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
