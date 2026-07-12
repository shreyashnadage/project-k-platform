"""API-level tests for VDP Wedge endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.vdp_wedge.app import app

client = TestClient(app)

VALID_IRN = "a" * 64


def test_ingest_endpoint_success():
    response = client.post(
        "/invoices/ingest",
        json={
            "irn": VALID_IRN,
            "anchor_gstin": "27AABCU9603R1ZM",
            "vendor_gstin": "27AADCB2230M1ZT",
            "amount": "500000.00",
            "issue_date": "2026-06-01",
            "due_date": "2026-09-01",
            "ims_status": "accepted",
            "repayment_routing_active": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["irn_valid"] is True
    assert data["kind1_eligible"] is True
    assert data["kind1_outcome"] == "pass"


def test_ingest_endpoint_invalid_gstin():
    response = client.post(
        "/invoices/ingest",
        json={
            "irn": VALID_IRN,
            "anchor_gstin": "SHORT",
            "vendor_gstin": "27AADCB2230M1ZT",
            "amount": "500000.00",
            "issue_date": "2026-06-01",
            "due_date": "2026-09-01",
        },
    )
    assert response.status_code == 422


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_kind1_check_not_found():
    response = client.post(
        "/invoices/kind1-check",
        json={
            "invoice_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404
