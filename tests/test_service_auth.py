"""Tests for the internal service-to-service auth middleware
(libs/common/service_auth.py) used by ddp_engine, vdp_wedge, trust_graph.
"""

from __future__ import annotations

import os
import subprocess
import sys

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.common import service_auth as sa


def _make_token() -> str:
    return pyjwt.encode({"sub": "la-orchestrator"}, "test-secret", algorithm="HS256")


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(sa.ServiceAuthMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/ddp/compute")
    def compute():
        return {"ok": True}

    return app


class TestServiceAuthDisabledByDefault:
    def test_passthrough_when_disabled(self, monkeypatch):
        monkeypatch.setattr(sa, "SERVICE_AUTH_ENABLED", False)
        client = TestClient(_build_test_app())
        response = client.get("/ddp/compute")
        assert response.status_code == 200


class TestServiceAuthEnabled:
    def test_health_always_passes(self, monkeypatch):
        monkeypatch.setattr(sa, "SERVICE_AUTH_ENABLED", True)
        client = TestClient(_build_test_app())
        response = client.get("/health")
        assert response.status_code == 200

    def test_protected_path_requires_bearer_token(self, monkeypatch):
        monkeypatch.setattr(sa, "SERVICE_AUTH_ENABLED", True)
        client = TestClient(_build_test_app())
        response = client.get("/ddp/compute")
        assert response.status_code == 401

    def test_protected_path_allows_valid_token(self, monkeypatch):
        monkeypatch.setattr(sa, "SERVICE_AUTH_ENABLED", True)
        client = TestClient(_build_test_app())
        token = _make_token()
        response = client.get("/ddp/compute", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_jwks_failure_fails_closed(self, monkeypatch):
        monkeypatch.setattr(sa, "SERVICE_AUTH_ENABLED", True)
        monkeypatch.setattr(sa, "KEYCLOAK_JWKS_URL", "http://fake-jwks.invalid/certs")

        class _BrokenJWKSClient:
            def get_signing_key_from_jwt(self, token):
                raise ConnectionError("unreachable")

        monkeypatch.setattr(sa, "_get_jwks_client", lambda: _BrokenJWKSClient())

        client = TestClient(_build_test_app())
        token = _make_token()
        response = client.get("/ddp/compute", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestServiceAuthStartupGuard:
    def test_enabled_without_jwks_raises_outside_sandbox(self):
        env = dict(os.environ)
        env.pop("INTEGRATION_MODE", None)
        env.pop("KEYCLOAK_JWKS_URL", None)
        env["SERVICE_AUTH_ENABLED"] = "true"
        result = subprocess.run(
            [sys.executable, "-c", "import libs.common.service_auth"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "KEYCLOAK_JWKS_URL" in result.stderr

    def test_sandbox_mode_allows_startup_without_jwks(self):
        env = dict(os.environ)
        env.pop("KEYCLOAK_JWKS_URL", None)
        env["SERVICE_AUTH_ENABLED"] = "true"
        env["INTEGRATION_MODE"] = "sandbox"
        result = subprocess.run(
            [sys.executable, "-c", "import libs.common.service_auth; print('OK')"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout
