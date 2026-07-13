"""Tests for Udyam verification — sandbox client, factory, and endpoint."""

from __future__ import annotations

import os

import pytest

@pytest.fixture(autouse=True)
def _sandbox_mode(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "sandbox")


class TestSandboxUdyamClient:
    @pytest.mark.asyncio
    async def test_known_number_returns_full_data(self):
        from ocen_sandbox import SandboxUdyamClient

        client = SandboxUdyamClient()
        result = await client.verify("UDYAM-MH-26-0123456")

        assert result.valid is True
        assert result.enterprise_name == "Shree Ganesh Auto Components"
        assert result.enterprise_type == "Micro"
        assert result.state == "Maharashtra"
        assert result.district == "Kolhapur"
        assert len(result.nic_codes) == 2

    @pytest.mark.asyncio
    async def test_unknown_valid_format_generates_data(self):
        from ocen_sandbox import SandboxUdyamClient

        client = SandboxUdyamClient()
        result = await client.verify("UDYAM-MH-01-9999999")

        assert result.valid is True
        assert result.enterprise_name == "Test Enterprise 9999999"
        assert result.state == "Maharashtra"

    @pytest.mark.asyncio
    async def test_invalid_format_returns_invalid(self):
        from ocen_sandbox import SandboxUdyamClient

        client = SandboxUdyamClient()
        result = await client.verify("INVALID-NUMBER")

        assert result.valid is False

    @pytest.mark.asyncio
    async def test_force_invalid_via_env(self, monkeypatch):
        monkeypatch.setenv("UDYAM_SANDBOX_VALID", "false")
        from ocen_sandbox import SandboxUdyamClient

        client = SandboxUdyamClient()
        result = await client.verify("UDYAM-MH-26-0123456")

        assert result.valid is False


class TestUdyamFactory:
    def test_sandbox_mode_returns_sandbox_client(self):
        from libs.integrations.factory import get_udyam_client
        from ocen_sandbox import SandboxUdyamClient

        client = get_udyam_client()
        assert isinstance(client, SandboxUdyamClient)

    def test_live_mode_gridlines(self, monkeypatch):
        monkeypatch.setenv("INTEGRATION_MODE", "live")
        monkeypatch.setenv("UDYAM_TSP_PROVIDER", "gridlines")
        monkeypatch.setenv("GRIDLINES_API_KEY", "test-key")

        from libs.integrations.factory import get_udyam_client
        from libs.integrations.udyam import GridlinesUdyamClient

        client = get_udyam_client()
        assert isinstance(client, GridlinesUdyamClient)

    def test_live_mode_surepass(self, monkeypatch):
        monkeypatch.setenv("INTEGRATION_MODE", "live")
        monkeypatch.setenv("UDYAM_TSP_PROVIDER", "surepass")
        monkeypatch.setenv("SUREPASS_API_KEY", "test-key")

        from libs.integrations.factory import get_udyam_client
        from libs.integrations.udyam import SurepassUdyamClient

        client = get_udyam_client()
        assert isinstance(client, SurepassUdyamClient)

    def test_live_mode_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("INTEGRATION_MODE", "live")
        monkeypatch.setenv("UDYAM_TSP_PROVIDER", "unknown")

        from libs.integrations.factory import get_udyam_client

        with pytest.raises(RuntimeError, match="Unknown UDYAM_TSP_PROVIDER"):
            get_udyam_client()


class TestUdyamEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from services.borrower_gateway.app import app

        return TestClient(app)

    def test_verify_udyam_valid(self, client):
        resp = client.post(
            "/vendors/verify-udyam",
            json={"udyam_number": "UDYAM-MH-26-0123456"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["enterprise_name"] == "Shree Ganesh Auto Components"
        assert data["enterprise_type"] == "Micro"

    def test_verify_udyam_invalid_format(self, client):
        resp = client.post(
            "/vendors/verify-udyam",
            json={"udyam_number": "BAD-FORMAT"},
        )
        assert resp.status_code == 422

    def test_register_with_udyam_auto_populates(self, client):
        resp = client.post(
            "/vendors/register",
            json={
                "name": "Test Vendor",
                "gstin": "27AADCB2230M1ZT",
                "phone": "9876543210",
                "udyam_number": "UDYAM-MH-26-0123456",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
