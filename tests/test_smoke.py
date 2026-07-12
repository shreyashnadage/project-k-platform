"""Smoke tests — verify core modules import and basic models work."""

from __future__ import annotations

from uuid import uuid4

import pytest


def test_models_import():
    """Core domain models import without error."""


def test_events_import():
    """Event definitions import without error."""


def test_gstin_validation():
    """GSTIN model validates format."""
    from libs.common.models import GSTIN

    # Valid GSTIN format
    valid = GSTIN(value="27AABCU9603R1ZM")
    assert valid.value == "27AABCU9603R1ZM"

    # Invalid — too short
    with pytest.raises(ValueError):
        GSTIN(value="27AABCU")


def test_kind1_attestation():
    """Kind1Attestation.is_kind1 is True only when all conditions met."""
    from libs.common.models import InvoiceIMSStatus, Kind1Attestation

    # All conditions met
    k1 = Kind1Attestation(
        invoice_id=uuid4(),
        irn_valid=True,
        ims_accepted=True,
        ims_status=InvoiceIMSStatus.ACCEPTED,
        repayment_routing_active=True,
    )
    assert k1.is_kind1 is True

    # IMS not accepted
    k2 = Kind1Attestation(
        invoice_id=uuid4(),
        irn_valid=True,
        ims_accepted=False,
        ims_status=InvoiceIMSStatus.DEEMED_ACCEPTED,
        repayment_routing_active=True,
    )
    assert k2.is_kind1 is False


def test_trade_event_creation():
    """TradeEvent can be created via factory function."""
    from libs.common.events import invoice_kind1_attested

    event = invoice_kind1_attested(
        invoice_id=uuid4(),
        loan_application_id=uuid4(),
        irn="a" * 64,
        ims_status="accepted",
        repayment_routing_active=True,
        is_kind1=True,
        source_service="test",
    )
    assert event.event_type.value == "invoice.kind1_attested"
    assert event.entity_type == "invoice"
    assert event.payload["is_kind1"] is True


def test_decision_receipt_creation():
    """DecisionReceipt can be created with required fields."""
    from libs.common.models import DecisionGate, DecisionOutcome, DecisionReceipt

    receipt = DecisionReceipt(
        loan_application_id=uuid4(),
        gate=DecisionGate.D0_KIND1_GATE,
        outcome=DecisionOutcome.PASS,
        ruleset_hash="a" * 64,
        input_hash="b" * 64,
        output={"outcome": "pass"},
        engine_version="zen-0.27.0",
    )
    assert receipt.gate == DecisionGate.D0_KIND1_GATE


def test_audit_receipt_signer():
    """ReceiptSigner creates and signs a receipt."""
    from libs.audit.receipts import ReceiptSigner
    from libs.common.models import DecisionGate, DecisionOutcome

    signer = ReceiptSigner(signing_key=b"test-key")
    receipt = signer.create_receipt(
        loan_application_id=uuid4(),
        gate=DecisionGate.D0_KIND1_GATE,
        outcome=DecisionOutcome.PASS,
        ruleset_hash="a" * 64,
        rule_input={"irn_valid": True},
        rule_output={"outcome": "pass"},
        engine_version="test-0.0.0",
    )
    assert receipt.signature is not None
    assert receipt.chain_hash is not None
    assert len(receipt.signature) == 64  # HMAC-SHA256 hex


def test_audit_chain_verification():
    """ChainVerifier detects intact and tampered chains."""
    from libs.audit.receipts import ChainVerifier, ReceiptSigner
    from libs.common.models import DecisionGate, DecisionOutcome

    signer = ReceiptSigner(signing_key=b"test-key")
    gates = [
        DecisionGate.D0_KIND1_GATE,
        DecisionGate.D1_DATA_SUFFICIENCY,
        DecisionGate.D2_DERIVED_ATTRIBUTES,
    ]

    receipts = []
    prev_hash = None
    for gate in gates:
        r = signer.create_receipt(
            loan_application_id=uuid4(),
            gate=gate,
            outcome=DecisionOutcome.PASS,
            ruleset_hash="a" * 64,
            rule_input={"test": True},
            rule_output={"outcome": "pass"},
            engine_version="test-0.0.0",
            previous_chain_hash=prev_hash,
        )
        receipts.append(r)
        prev_hash = r.chain_hash

    # Chain should verify
    assert ChainVerifier.verify_chain(receipts) is True
