"""Tests for sandbox integration clients."""

from __future__ import annotations

import pytest

from libs.integrations.factory import (
    get_aa_client,
    get_gst_client,
    get_lender_client,
    get_ocen_client,
)


@pytest.fixture(autouse=True)
def _sandbox_mode(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "sandbox")


async def test_sandbox_aa_client_consent_flow():
    aa = get_aa_client()
    consent = await aa.create_consent("27AADCB2230M1ZT", "loan_origination", 12)
    assert consent.consent_id.startswith("sandbox-consent-")
    assert consent.status == "approved"

    status = await aa.check_consent_status(consent.consent_id)
    assert status.status == "approved"

    data = await aa.fetch_financial_data(consent.consent_id)
    assert data.months_available == 6
    assert len(data.bank_statements) > 0
    assert len(data.gst_returns) > 0


async def test_sandbox_ocen_client_submission_flow():
    ocen = get_ocen_client()
    submission = await ocen.submit_application("app-001", ["lender-001"], {"test": True})
    assert submission.submission_id.startswith("sandbox-sub-")
    assert "lender-001" in submission.lender_acks

    offers = await ocen.check_offer_status(submission.submission_id)
    assert offers.status == "offer_available"
    assert len(offers.offers) == 1
    assert offers.offers[0]["lender_id"] == "sandbox-lender-nbfc-001"

    acceptance = await ocen.accept_offer("offer-001")
    assert acceptance.status == "accepted"


async def test_sandbox_gst_client_irn_validation():
    gst = get_gst_client()
    valid_irn = "a" * 64
    result = await gst.validate_irn(valid_irn)
    assert result.valid is True

    invalid_irn = "not-valid"
    result = await gst.validate_irn(invalid_irn)
    assert result.valid is False


async def test_sandbox_gst_client_gstin_validation():
    gst = get_gst_client()
    result = await gst.validate_gstin("27AADCB2230M1ZT")
    assert result.valid is True
    assert result.trade_name is not None

    result = await gst.validate_gstin("INVALID")
    assert result.valid is False


async def test_sandbox_gst_client_ims_status():
    gst = get_gst_client()
    result = await gst.check_ims_status("a" * 64, "27AABCU9603R1ZM")
    assert result.status == "accepted"


async def test_sandbox_lender_auto_approve():
    lender = get_lender_client(auto_approve=True)
    webhook_id = await lender.register_webhook("app-001", "http://callback.test/hook")
    assert "sandbox-webhook" in webhook_id

    decision = await lender.poll_decision("app-001")
    assert decision.status == "approved"
    assert decision.amount_sanctioned is not None


async def test_sandbox_lender_reject():
    lender = get_lender_client(auto_approve=False)
    decision = await lender.poll_decision("app-001")
    assert decision.status == "rejected"


def test_factory_returns_sandbox_clients():
    assert type(get_aa_client()).__name__ == "SandboxAAClient"
    assert type(get_ocen_client()).__name__ == "SandboxOCENClient"
    assert type(get_gst_client()).__name__ == "SandboxGSTClient"
    assert type(get_lender_client()).__name__ == "SandboxLenderClient"


def test_factory_fails_without_integration_mode(monkeypatch):
    monkeypatch.delenv("INTEGRATION_MODE", raising=False)
    with pytest.raises(RuntimeError, match="INTEGRATION_MODE"):
        get_aa_client()


def test_factory_fails_with_invalid_mode(monkeypatch):
    monkeypatch.setenv("INTEGRATION_MODE", "production")
    with pytest.raises(RuntimeError, match="INTEGRATION_MODE"):
        get_aa_client()
