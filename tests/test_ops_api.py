"""Tests for the Ops Command API endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from services.borrower_gateway.app import app

    return TestClient(app)


@pytest.fixture
def ops_headers():
    return {"Authorization": "Bearer dev-ops-key-change-in-production"}


class TestOpsHold:
    def test_hold_requires_auth(self, client):
        resp = client.post(
            "/ops/hold",
            json={
                "application_id": str(uuid.uuid4()),
                "reason": "Suspicious activity",
                "held_by": "admin@company.com",
            },
        )
        assert resp.status_code == 422 or resp.status_code == 401

    def test_hold_rejects_bad_key(self, client):
        resp = client.post(
            "/ops/hold",
            json={
                "application_id": str(uuid.uuid4()),
                "reason": "Suspicious activity",
                "held_by": "admin@company.com",
            },
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_hold_validation(self, client, ops_headers):
        resp = client.post(
            "/ops/hold",
            json={
                "application_id": str(uuid.uuid4()),
                "reason": "ab",  # too short
                "held_by": "admin",
            },
            headers=ops_headers,
        )
        assert resp.status_code == 422


class TestOpsFlag:
    def test_flag_success(self, client, ops_headers):
        resp = client.post(
            "/ops/flag",
            json={
                "application_id": str(uuid.uuid4()),
                "flag_type": "manual_review",
                "note": "Vendor has multiple applications in short window",
                "flagged_by": "ops@company.com",
            },
            headers=ops_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "flag"


class TestOpsEscalate:
    def test_escalate_success(self, client, ops_headers):
        resp = client.post(
            "/ops/escalate",
            json={
                "application_id": str(uuid.uuid4()),
                "reason": "DPD > 30 days",
                "escalated_by": "collections@company.com",
            },
            headers=ops_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "escalate"


class TestOpsApplications:
    def test_list_active_requires_auth(self, client):
        resp = client.get("/ops/applications/active")
        assert resp.status_code in (401, 422)

    def test_list_active_empty(self, client, ops_headers):
        resp = client.get("/ops/applications/active", headers=ops_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["applications"] == []

    def test_get_detail_not_found(self, client, ops_headers):
        resp = client.get(
            f"/ops/applications/{uuid.uuid4()}",
            headers=ops_headers,
        )
        assert resp.status_code == 404


class TestVendorRegistration:
    def test_self_register(self, client):
        resp = client.post(
            "/vendors/register",
            json={
                "name": "Test Vendor Pvt Ltd",
                "gstin": "27AADCB2230M1ZT",
                "phone": "9876543210",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert "vendor_id" in data

    def test_activate_vendor(self, client):
        resp = client.post(
            "/vendors/activate",
            json={
                "invite_token": "some-token-here",
                "name": "Activated Vendor",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"


class TestVendorInvite:
    def test_invite_requires_auth(self, client):
        resp = client.post(
            "/ops/vendor/invite",
            json={
                "name": "New Vendor",
                "gstin": "27AADCB2230M1ZT",
                "phone": "9876543210",
                "invited_by": "admin",
            },
        )
        assert resp.status_code in (401, 422)

    def test_invite_success(self, client, ops_headers):
        resp = client.post(
            "/ops/vendor/invite",
            json={
                "name": "New Vendor Pvt Ltd",
                "gstin": "27AADCB2230M1ZT",
                "phone": "9876543210",
                "invited_by": "ops@company.com",
            },
            headers=ops_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "invited"
        assert "invite_token" in data
        assert "invite_link" in data


class TestAnchorOnboard:
    def test_onboard_success(self, client, ops_headers):
        resp = client.post(
            "/ops/anchor/onboard",
            json={
                "name": "Bajaj Auto Ltd",
                "gstin": "27AAACT2727Q1ZW",
                "sector": "auto-ancillary",
                "region": "pune",
                "onboarded_by": "ops@company.com",
            },
            headers=ops_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "onboarded"
        assert "anchor_id" in data


@pytest.mark.integration
class TestVendorPersistenceAgainstRealPostgres:
    """Requires `make up`. Proves the GATEWAY_USE_DB=true code path in
    ops_api.py actually persists and enforces uniqueness/token validity —
    the previous implementation silently created a fresh vendor_id on every
    call, including for duplicate GSTINs and stale/reused invite tokens."""

    @pytest.fixture(autouse=True)
    def _use_real_db(self, monkeypatch):
        monkeypatch.setenv("GATEWAY_USE_DB", "true")

    def test_duplicate_gstin_self_registration_is_rejected(self, client):
        payload = {
            "name": "Duplicate GSTIN Vendor",
            "gstin": "29AADCB2230M1ZQ",
            "phone": "9876500001",
        }
        first = client.post("/vendors/register", json=payload)
        assert first.status_code == 200

        second = client.post("/vendors/register", json=payload)
        assert second.status_code == 409, (
            "A second registration with the same GSTIN must be rejected, "
            "not silently create a second vendor_id"
        )

    def test_duplicate_gstin_invite_is_rejected(self, client, ops_headers):
        payload = {
            "name": "Duplicate Invite Vendor",
            "gstin": "29AADCB2230M1ZR",
            "phone": "9876500002",
            "invited_by": "ops@company.com",
        }
        first = client.post("/ops/vendor/invite", json=payload, headers=ops_headers)
        assert first.status_code == 200

        second = client.post("/ops/vendor/invite", json=payload, headers=ops_headers)
        assert second.status_code == 409

    def test_activate_with_unknown_token_returns_404(self, client):
        resp = client.post(
            "/vendors/activate",
            json={"invite_token": "this-token-was-never-issued"},
        )
        assert resp.status_code == 404

    def test_activate_twice_with_same_token_fails_second_time(self, client, ops_headers):
        invite = client.post(
            "/ops/vendor/invite",
            json={
                "name": "Reactivation Vendor",
                "gstin": "29AADCB2230M1ZS",
                "phone": "9876500003",
                "invited_by": "ops@company.com",
            },
            headers=ops_headers,
        )
        assert invite.status_code == 200
        token = invite.json()["invite_token"]

        first_activation = client.post("/vendors/activate", json={"invite_token": token})
        assert first_activation.status_code == 200

        second_activation = client.post("/vendors/activate", json={"invite_token": token})
        assert second_activation.status_code in (404, 422), (
            "A one-time invite token must not activate a second time — "
            "the token is cleared on first use"
        )
