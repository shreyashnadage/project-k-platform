"""VDP Wedge service models — invoice ingestion and Kind 1 attestation."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


class InvoiceIngestionRequest(BaseModel):
    """Request to ingest an invoice from the anchor's ERP."""

    irn: str = Field(..., description="Invoice Reference Number from GST e-invoicing portal")
    anchor_gstin: str = Field(..., min_length=15, max_length=15)
    vendor_gstin: str = Field(..., min_length=15, max_length=15)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="INR")
    issue_date: date
    due_date: date
    ims_status: str = Field(
        default="pending", description="GST IMS status: pending/accepted/deemed_accepted/rejected"
    )
    repayment_routing_active: bool = Field(default=False)


class InvoiceIngestionResponse(BaseModel):
    """Response after invoice ingestion."""

    invoice_id: UUID
    irn: str
    irn_valid: bool
    ims_status: str
    kind1_eligible: bool
    kind1_outcome: str | None = None
    kind1_reason: str | None = None


class Kind1CheckRequest(BaseModel):
    """Request to evaluate Kind 1 attestation for an invoice."""

    invoice_id: UUID


class Kind1CheckResponse(BaseModel):
    """Result of Kind 1 gate evaluation."""

    invoice_id: UUID
    outcome: str
    reason: str
    ruleset_hash: str
    receipt_id: str | None = None
