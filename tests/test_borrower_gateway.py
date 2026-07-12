"""Tests for Borrower Gateway — loan application lifecycle."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from services.borrower_gateway.app import app
from services.borrower_gateway.models import LoanApplicationRequest
from services.borrower_gateway.service import BorrowerGatewayService

client = TestClient(app)


def test_initiate_application():
    svc = BorrowerGatewayService()
    request = LoanApplicationRequest(
        invoice_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        amount_requested=Decimal("500000.00"),
    )
    response = svc.initiate_application(request)
    assert response.status == "initiated"
    assert response.workflow_id is not None


def test_get_status():
    svc = BorrowerGatewayService()
    request = LoanApplicationRequest(
        invoice_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        amount_requested=Decimal("500000.00"),
    )
    resp = svc.initiate_application(request)
    status = svc.get_status(resp.application_id)
    assert status.status == "initiated"
    assert status.current_gate == "d0_kind1"


def test_get_status_not_found():
    svc = BorrowerGatewayService()
    with pytest.raises(KeyError):
        svc.get_status(uuid.uuid4())


def test_update_gate():
    svc = BorrowerGatewayService()
    request = LoanApplicationRequest(
        invoice_id=uuid.uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        amount_requested=Decimal("500000.00"),
    )
    resp = svc.initiate_application(request)
    svc.update_gate(resp.application_id, "d1_data_sufficiency", "in_progress")
    status = svc.get_status(resp.application_id)
    assert status.current_gate == "d1_data_sufficiency"
    assert status.status == "in_progress"


def test_api_apply_endpoint():
    invoice_id = str(uuid.uuid4())
    response = client.post(
        "/loans/apply",
        json={
            "invoice_id": invoice_id,
            "vendor_gstin": "27AADCB2230M1ZT",
            "anchor_gstin": "27AABCU9603R1ZM",
            "amount_requested": "500000.00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "initiated"
    assert data["workflow_id"] is not None


def test_api_status_not_found():
    response = client.post(
        "/loans/status",
        json={
            "application_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404


def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "borrower-gateway"
