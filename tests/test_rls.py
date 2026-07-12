"""Tests for PostgreSQL RLS tenant-context plumbing (libs/db/rls.py) and
the middleware's tenant-claim extraction (libs/common/middleware.py).

No live Postgres is required — set_tenant_context/clear_tenant_context are
tested against a mocked AsyncSession, asserting the exact SQL/params sent
(sqlalchemy.text() wrapping, set_config not raw SET LOCAL).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from libs.common import middleware as mw
from libs.db import rls


@pytest.fixture(autouse=True)
def _reset_caches():
    rls.reset_tenancy_cache()
    rls.tenant_id_var.set(None)
    rls.resolved_roles_var.set(frozenset())
    yield
    rls.reset_tenancy_cache()
    rls.tenant_id_var.set(None)
    rls.resolved_roles_var.set(frozenset())


def _write_tenancy_config(tmp_path, **overrides):
    content = (
        "tenant_claim_path: org_id\n"
        "session_variable: app.tenant_id\n"
        "bypass_roles:\n"
        "  - platform-admin\n"
        "  - operations\n"
    )
    config_file = tmp_path / "tenancy.yaml"
    config_file.write_text(content)
    return config_file


class TestSetTenantContext:
    async def test_uses_set_config_not_raw_set_local(self, tmp_path, monkeypatch):
        _write_tenancy_config(tmp_path)
        monkeypatch.setenv("TENANCY_CONFIG_PATH", str(tmp_path / "tenancy.yaml"))
        rls.reset_tenancy_cache()

        session = AsyncMock()
        await rls.set_tenant_context(session, "27AADCB2230M1ZT")

        session.execute.assert_awaited_once()
        call_args = session.execute.call_args
        compiled_sql = str(call_args.args[0])
        assert "set_config" in compiled_sql
        assert "SET LOCAL" not in compiled_sql
        assert call_args.args[1] == {"variable": "app.tenant_id", "tenant_id": "27AADCB2230M1ZT"}

    async def test_clear_uses_bypass_sentinel_not_empty_string(self, tmp_path, monkeypatch):
        _write_tenancy_config(tmp_path)
        monkeypatch.setenv("TENANCY_CONFIG_PATH", str(tmp_path / "tenancy.yaml"))
        rls.reset_tenancy_cache()

        session = AsyncMock()
        await rls.clear_tenant_context(session)

        call_args = session.execute.call_args
        assert call_args.args[1]["sentinel"] == rls.RLS_BYPASS_SENTINEL
        assert call_args.args[1]["sentinel"] != ""


class TestTenantScopedSession:
    async def test_no_tenant_resolved_yields_unscoped_session(self, monkeypatch):
        rls.tenant_id_var.set(None)

        fake_session = AsyncMock()

        async def fake_get_session():
            yield fake_session

        monkeypatch.setattr(rls, "get_session", fake_get_session)

        sessions = [s async for s in rls.tenant_scoped_session()]
        assert sessions == [fake_session]
        fake_session.execute.assert_not_awaited()

    async def test_bypass_role_clears_context(self, tmp_path, monkeypatch):
        _write_tenancy_config(tmp_path)
        monkeypatch.setenv("TENANCY_CONFIG_PATH", str(tmp_path / "tenancy.yaml"))
        rls.reset_tenancy_cache()

        rls.tenant_id_var.set("27AADCB2230M1ZT")
        rls.resolved_roles_var.set(frozenset({"platform-admin"}))

        fake_session = AsyncMock()

        async def fake_get_session():
            yield fake_session

        monkeypatch.setattr(rls, "get_session", fake_get_session)

        async for _ in rls.tenant_scoped_session():
            pass

        call_args = fake_session.execute.call_args
        assert call_args.args[1]["sentinel"] == rls.RLS_BYPASS_SENTINEL

    async def test_scoped_role_sets_tenant_context(self, tmp_path, monkeypatch):
        _write_tenancy_config(tmp_path)
        monkeypatch.setenv("TENANCY_CONFIG_PATH", str(tmp_path / "tenancy.yaml"))
        rls.reset_tenancy_cache()

        rls.tenant_id_var.set("27AADCB2230M1ZT")
        rls.resolved_roles_var.set(frozenset({"anchor-manager"}))

        fake_session = AsyncMock()

        async def fake_get_session():
            yield fake_session

        monkeypatch.setattr(rls, "get_session", fake_get_session)

        async for _ in rls.tenant_scoped_session():
            pass

        call_args = fake_session.execute.call_args
        assert call_args.args[1]["tenant_id"] == "27AADCB2230M1ZT"


class TestMiddlewareTenantClaimExtraction:
    def test_extracts_simple_claim(self):
        decoded = {"org_id": "27AADCB2230M1ZT", "realm_access": {"roles": ["anchor-manager"]}}
        assert mw._extract_tenant_claim(decoded) == "27AADCB2230M1ZT"

    def test_extracts_dotted_claim_path(self, monkeypatch, tmp_path):
        config_file = tmp_path / "tenancy.yaml"
        config_file.write_text("tenant_claim_path: custom.tenant_id\n")
        monkeypatch.setenv("TENANCY_CONFIG_PATH", str(config_file))
        rls.reset_tenancy_cache()
        try:
            decoded = {"custom": {"tenant_id": "36AABCY9234H1Z5"}}
            assert mw._extract_tenant_claim(decoded) == "36AABCY9234H1Z5"
        finally:
            rls.reset_tenancy_cache()

    def test_missing_claim_returns_none(self):
        assert mw._extract_tenant_claim({"sub": "user-123"}) is None

    def test_non_string_claim_returns_none(self):
        assert mw._extract_tenant_claim({"org_id": {"nested": "object"}}) is None


class TestMiddlewareSetsContextVarsAfterAuth:
    def test_dispatch_sets_tenant_and_roles_on_success(self, monkeypatch):
        import jwt as pyjwt
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        monkeypatch.setattr(mw, "RBAC_ENABLED", True)
        mw.reset_authz_cache()

        app = FastAPI()
        app.add_middleware(mw.DPDPRBACMiddleware)

        captured = {}

        @app.get("/ops/hold")
        def ops_hold():
            captured["tenant_id"] = rls.tenant_id_var.get()
            captured["roles"] = rls.resolved_roles_var.get()
            return {"ok": True}

        token = pyjwt.encode(
            {"realm_access": {"roles": ["operations"]}, "org_id": "27AADCB2230M1ZT"},
            "secret",
            algorithm="HS256",
        )
        client = TestClient(app)
        response = client.get("/ops/hold", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert captured["tenant_id"] == "27AADCB2230M1ZT"
        assert captured["roles"] == frozenset({"operations"})
