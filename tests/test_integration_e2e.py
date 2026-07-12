"""End-to-end integration test — full loan origination flow.

Requires: docker compose up (Postgres, Redpanda, Temporal)
Run with: pytest -m integration
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from services.borrower_gateway.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.integration
class TestLoanOriginationE2E:
    def test_apply_returns_initiated(self, client):
        response = client.post(
            "/loans/apply",
            json={
                "invoice_id": str(uuid.uuid4()),
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "27AAACT2727Q1ZW",
                "amount_requested": "250000.00",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "initiated"
        assert "application_id" in data
        assert data["workflow_id"].startswith("loan-")

    def test_idempotency_returns_same_application(self, client):
        idem_key = f"test-{uuid.uuid4()}"
        payload = {
            "invoice_id": str(uuid.uuid4()),
            "vendor_gstin": "27AADCB2230M1ZT",
            "anchor_gstin": "27AAACT2727Q1ZW",
            "amount_requested": "100000.00",
            "idempotency_key": idem_key,
        }

        r1 = client.post("/loans/apply", json=payload)
        r2 = client.post("/loans/apply", json=payload)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["application_id"] == r2.json()["application_id"]

    def test_status_after_apply(self, client):
        r = client.post(
            "/loans/apply",
            json={
                "invoice_id": str(uuid.uuid4()),
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "27AAACT2727Q1ZW",
                "amount_requested": "500000.00",
            },
        )
        app_id = r.json()["application_id"]

        status_r = client.post(
            "/loans/status",
            json={"application_id": app_id},
        )
        assert status_r.status_code == 200
        assert status_r.json()["status"] == "initiated"

    def test_status_not_found(self, client):
        response = client.post(
            "/loans/status",
            json={"application_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "borrower-gateway"

    def test_ocen_callback_without_jws_passes(self, client):
        response = client.post(
            "/v4.0.0alpha/loanApplications/generateOffersResponse",
            json={
                "metadata": {
                    "trace_id": "trace-123",
                    "timestamp": "2026-07-12T10:00:00Z",
                    "org_id": "org-1",
                    "version": "4.0.0alpha",
                },
                "loan_applications": [],
            },
        )
        assert response.status_code == 200
