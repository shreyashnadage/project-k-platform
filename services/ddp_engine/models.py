"""DDP Engine models — derived data computation for lenders."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


class DerivedDataRequest(BaseModel):
    """Request to compute derived attributes for a loan application."""

    loan_application_id: UUID
    vendor_gstin: str = Field(..., min_length=15, max_length=15)
    anchor_gstin: str = Field(..., min_length=15, max_length=15)
    invoice_amount: Decimal
    gst_returns_months: int = Field(default=12, ge=1, le=36)


class DerivedDataResponse(BaseModel):
    """Computed derived attributes — this is the DDP function output."""

    loan_application_id: UUID
    vendor_gstin: str
    anchor_gstin: str
    attributes: DerivedAttributes
    risk_flags: list[RiskFlag]
    ruleset_hash: str
    computed_at: datetime


class DerivedAttributes(BaseModel):
    """Derived financial metrics for the vendor-anchor relationship."""

    dso_days: int = Field(..., description="Days Sales Outstanding")
    dpo_days: int = Field(..., description="Days Payable Outstanding")
    ccc_days: int = Field(..., description="Cash Conversion Cycle")
    revenue_concentration: Decimal = Field(..., description="% of revenue from this anchor")
    dilution_rate: Decimal = Field(..., description="Invoice adjustment rate")
    anchor_payment_history_score: Decimal = Field(..., description="0-100 anchor reliability")
    anchor_avg_dpd: int = Field(..., description="Anchor's average days payment delay")
    gst_compliance_score: Decimal = Field(..., description="0-100 GST filing regularity")
    vintage_months: int = Field(..., description="Relationship duration in months")


class RiskFlag(BaseModel):
    """Risk flag raised during derived attribute computation."""

    flag_code: str
    severity: str = Field(..., description="low|medium|high|critical")
    description: str
    threshold: str | None = None
    actual_value: str | None = None
