"""Tests for DDP Engine — derived data computation."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from services.ddp_engine.app import app
from services.ddp_engine.models import DerivedDataRequest
from services.ddp_engine.service import DDPEngineService

client = TestClient(app)


def test_compute_derived_data():
    svc = DDPEngineService()
    request = DerivedDataRequest(
        loan_application_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        invoice_amount=Decimal("500000.00"),
        gst_returns_months=12,
    )
    response = svc.compute_derived_data(request)
    assert response.attributes.dso_days > 0
    assert response.attributes.gst_compliance_score > Decimal("0")
    assert response.ruleset_hash is not None


def test_no_risk_flags_for_healthy_vendor():
    svc = DDPEngineService()
    request = DerivedDataRequest(
        loan_application_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        invoice_amount=Decimal("500000.00"),
        gst_returns_months=12,
    )
    response = svc.compute_derived_data(request)
    assert len(response.risk_flags) == 0


def test_low_vintage_flag():
    svc = DDPEngineService()
    request = DerivedDataRequest(
        loan_application_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        invoice_amount=Decimal("500000.00"),
        gst_returns_months=3,
    )
    response = svc.compute_derived_data(request)
    flag_codes = [f.flag_code for f in response.risk_flags]
    assert "LOW_VINTAGE" in flag_codes


def test_api_compute_endpoint():
    response = client.post(
        "/ddp/compute",
        json={
            "loan_application_id": str(uuid.uuid4()),
            "vendor_gstin": "27AADCB2230M1ZT",
            "anchor_gstin": "27AABCU9603R1ZM",
            "invoice_amount": "500000.00",
            "gst_returns_months": 12,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "attributes" in data
    assert "risk_flags" in data


def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "ddp-engine"
