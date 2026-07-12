"""Frozen trade event definitions.

Every event is an immutable fact appended to the Redpanda stream.
Schema is versioned and backward-compatible only — breaking changes
create a new event type, never mutate an existing one.

Events are the SINGLE source of truth for the Trust Graph.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from decimal import Decimal

# ─── Event Envelope ─────────────────────────────────────────


SCHEMA_VERSION = "1.0.0"


class EventType(enum.StrEnum):
    """Canonical event types in the trade-event stream."""

    # Anchor / vendor lifecycle
    ANCHOR_ONBOARDED = "anchor.onboarded"
    VENDOR_ONBOARDED = "vendor.onboarded"
    VENDOR_GSTIN_VALIDATED = "vendor.gstin_validated"
    REPAYMENT_ROUTING_ACTIVATED = "anchor.repayment_routing_activated"

    # Invoice lifecycle
    INVOICE_CAPTURED = "invoice.captured"
    INVOICE_IRN_VALIDATED = "invoice.irn_validated"
    INVOICE_IMS_STATUS_UPDATED = "invoice.ims_status_updated"
    INVOICE_KIND1_ATTESTED = "invoice.kind1_attested"

    # Loan lifecycle
    LOAN_APPLICATION_CREATED = "loan.application_created"
    LOAN_AA_CONSENT_REQUESTED = "loan.aa_consent_requested"
    LOAN_AA_DATA_RECEIVED = "loan.aa_data_received"
    LOAN_DECISION_EVALUATED = "loan.decision_evaluated"
    LOAN_DERIVED_COMPUTED = "loan.derived_computed"
    LOAN_LENDER_MATCHED = "loan.lender_matched"
    LOAN_SUBMITTED_TO_LENDER = "loan.submitted_to_lender"
    LOAN_OFFER_RECEIVED = "loan.offer_received"
    LOAN_OFFER_ACCEPTED = "loan.offer_accepted"
    LOAN_DISBURSED = "loan.disbursed"
    LOAN_REPAYMENT_OBSERVED = "loan.repayment_observed"
    LOAN_CLOSED = "loan.closed"
    LOAN_REJECTED = "loan.rejected"

    # Ops actions
    OPS_HOLD_APPLIED = "ops.hold_applied"
    OPS_HOLD_RELEASED = "ops.hold_released"
    OPS_FLAG_ADDED = "ops.flag_added"
    OPS_ESCALATED = "ops.escalated"

    # Vendor / Anchor onboarding
    VENDOR_INVITED = "vendor.invited"
    VENDOR_ACTIVATED = "vendor.activated"
    ANCHOR_ROUTING_UPDATED = "anchor.routing_updated"

    # DDP
    DDP_PACKAGE_ISSUED = "ddp.package_issued"
    DDP_VC_ISSUED = "ddp.vc_issued"


class TradeEvent(BaseModel):
    """The immutable event envelope. All events on the stream use this shape.

    topic: ocen.trade-events.v1
    key: {entity_type}:{entity_id} (e.g. "loan:uuid" or "invoice:uuid")
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    schema_version: str = SCHEMA_VERSION
    entity_type: str  # "anchor", "vendor", "invoice", "loan", "ddp"
    entity_id: UUID
    correlation_id: UUID | None = None  # links related events (e.g. loan_application_id)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: EventMetadata = Field(default_factory=lambda: EventMetadata())
    occurred_at: datetime = Field(default_factory=datetime.utcnow)

    def topic_key(self) -> str:
        return f"{self.entity_type}:{self.entity_id}"


class EventMetadata(BaseModel):
    """Metadata attached to every event for tracing and audit."""

    source_service: str = ""
    trace_id: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    actor_id: str | None = None  # user or system that triggered it
    idempotency_key: str | None = None


# ─── Event Factories ────────────────────────────────────────
# Convenience constructors that enforce the correct entity_type and payload shape.


def invoice_kind1_attested(
    invoice_id: UUID,
    loan_application_id: UUID,
    irn: str,
    ims_status: str,
    repayment_routing_active: bool,
    is_kind1: bool,
    **meta_kwargs: Any,
) -> TradeEvent:
    return TradeEvent(
        event_type=EventType.INVOICE_KIND1_ATTESTED,
        entity_type="invoice",
        entity_id=invoice_id,
        correlation_id=loan_application_id,
        payload={
            "irn": irn,
            "ims_status": ims_status,
            "repayment_routing_active": repayment_routing_active,
            "is_kind1": is_kind1,
        },
        metadata=EventMetadata(**meta_kwargs),
    )


def loan_decision_evaluated(
    loan_application_id: UUID,
    gate: str,
    outcome: str,
    ruleset_hash: str,
    input_hash: str,
    receipt_id: UUID,
    **meta_kwargs: Any,
) -> TradeEvent:
    return TradeEvent(
        event_type=EventType.LOAN_DECISION_EVALUATED,
        entity_type="loan",
        entity_id=loan_application_id,
        correlation_id=loan_application_id,
        payload={
            "gate": gate,
            "outcome": outcome,
            "ruleset_hash": ruleset_hash,
            "input_hash": input_hash,
            "receipt_id": str(receipt_id),
        },
        metadata=EventMetadata(**meta_kwargs),
    )


def loan_repayment_observed(
    loan_application_id: UUID,
    amount: Decimal,
    paid_by_anchor: bool,
    payment_reference: str,
    **meta_kwargs: Any,
) -> TradeEvent:
    return TradeEvent(
        event_type=EventType.LOAN_REPAYMENT_OBSERVED,
        entity_type="loan",
        entity_id=loan_application_id,
        correlation_id=loan_application_id,
        payload={
            "amount": str(amount),
            "paid_by_anchor": paid_by_anchor,
            "payment_reference": payment_reference,
        },
        metadata=EventMetadata(**meta_kwargs),
    )
