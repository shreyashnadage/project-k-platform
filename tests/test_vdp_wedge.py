"""Tests for VDP Wedge — invoice ingestion and Kind 1 attestation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from libs.zen_rules.engine import ZenDecisionEngine
from services.vdp_wedge.models import InvoiceIngestionRequest
from services.vdp_wedge.service import VDPWedgeService

VALID_IRN = "a" * 64  # 64-char hex string


@pytest.fixture
def service():
    engine = ZenDecisionEngine("rules/")
    return VDPWedgeService(engine)


def _make_request(**overrides) -> InvoiceIngestionRequest:
    defaults = {
        "irn": VALID_IRN,
        "anchor_gstin": "27AABCU9603R1ZM",
        "vendor_gstin": "27AADCB2230M1ZT",
        "amount": Decimal("500000.00"),
        "issue_date": date(2026, 6, 1),
        "due_date": date(2026, 9, 1),
        "ims_status": "accepted",
        "repayment_routing_active": True,
    }
    defaults.update(overrides)
    return InvoiceIngestionRequest(**defaults)


def test_ingest_invoice_kind1_pass(service: VDPWedgeService):
    """Invoice with all Kind 1 conditions met passes."""
    response = service.ingest_invoice(_make_request())
    assert response.irn_valid is True
    assert response.kind1_eligible is True
    assert response.kind1_outcome == "pass"


def test_ingest_invoice_kind1_flag_deemed_accepted(service: VDPWedgeService):
    """Deemed accepted IMS status results in flag."""
    response = service.ingest_invoice(_make_request(ims_status="deemed_accepted"))
    assert response.kind1_eligible is False
    assert response.kind1_outcome == "flag"


def test_ingest_invoice_invalid_irn(service: VDPWedgeService):
    """Invalid IRN skips Kind 1 evaluation."""
    response = service.ingest_invoice(_make_request(irn="not-a-valid-irn"))
    assert response.irn_valid is False
    assert response.kind1_eligible is False
    assert response.kind1_outcome is None


def test_ingest_invoice_pending_ims(service: VDPWedgeService):
    """Pending IMS status skips Kind 1 evaluation."""
    response = service.ingest_invoice(_make_request(ims_status="pending"))
    assert response.kind1_eligible is False


def test_ingest_invoice_no_routing(service: VDPWedgeService):
    """No repayment routing skips Kind 1 evaluation."""
    response = service.ingest_invoice(_make_request(repayment_routing_active=False))
    assert response.kind1_eligible is False


def test_check_kind1_existing_invoice(service: VDPWedgeService):
    """Can run Kind 1 check on a previously ingested invoice."""
    ingest_resp = service.ingest_invoice(_make_request())
    check_resp = service.check_kind1(ingest_resp.invoice_id)
    assert check_resp.outcome == "pass"
    assert check_resp.ruleset_hash


def test_check_kind1_missing_invoice(service: VDPWedgeService):
    """Kind 1 check on non-existent invoice raises KeyError."""
    import uuid

    with pytest.raises(KeyError):
        service.check_kind1(uuid.uuid4())
