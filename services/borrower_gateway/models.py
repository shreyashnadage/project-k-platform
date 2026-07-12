"""Borrower Gateway models — loan application requests and responses."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


class LoanApplicationRequest(BaseModel):
    """Request from borrower (vendor) to initiate a loan application."""

    invoice_id: UUID
    vendor_gstin: str = Field(..., min_length=15, max_length=15)
    anchor_gstin: str = Field(..., min_length=15, max_length=15)
    amount_requested: Decimal = Field(..., gt=0)
    idempotency_key: str | None = None


class LoanApplicationResponse(BaseModel):
    """Response after loan application is initiated."""

    application_id: UUID
    invoice_id: UUID
    status: str
    workflow_id: str | None = None
    message: str


class LoanApplicationStatus(BaseModel):
    """Current status of a loan application."""

    application_id: UUID
    status: str
    current_gate: str | None = None
    amount_requested: Decimal | None = None
    amount_sanctioned: Decimal | None = None
    lender_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LoanOfferResponse(BaseModel):
    """Loan offer from a lender."""

    application_id: UUID
    lender_id: str
    lender_name: str
    amount_offered: Decimal
    interest_rate: Decimal
    tenure_days: int
    terms: dict[str, str] = Field(default_factory=dict)


class InvoiceCapturedRequest(BaseModel):
    """Invoice captured from ERP (ERPNext/Frappe connector)."""

    irn: str = Field(..., min_length=64, max_length=64)
    invoice_number: str
    vendor_gstin: str = Field(..., min_length=15, max_length=15)
    anchor_gstin: str = Field(..., min_length=15, max_length=15)
    amount: Decimal = Field(..., gt=0)
    invoice_date: str
    due_date: str
    currency: str = "INR"
    participant_id: str | None = None


class InvoiceCapturedResponse(BaseModel):
    """Response after invoice is captured."""

    invoice_id: UUID
    irn: str
    status: str
    message: str
