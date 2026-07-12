"""Ops Command API models — Frappe back-office → Platform."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field

# ─── Ops Command Requests ──────────────────────────────────────


class OpsHoldRequest(BaseModel):
    """Hold an application before OCEN submission."""

    application_id: UUID
    reason: str = Field(..., min_length=3, max_length=500)
    held_by: str = Field(..., description="Frappe user who initiated the hold")


class OpsReleaseRequest(BaseModel):
    """Release a held application."""

    application_id: UUID
    released_by: str


class OpsFlagRequest(BaseModel):
    """Add an ops annotation/flag to an application."""

    application_id: UUID
    flag_type: str = Field(..., description="e.g. suspicious, manual_review, priority")
    note: str = Field(..., max_length=1000)
    flagged_by: str


class OpsEscalateRequest(BaseModel):
    """Escalate to collections (post-disbursement only)."""

    application_id: UUID
    reason: str
    escalated_by: str


# ─── Ops Command Responses ─────────────────────────────────────


class OpsCommandResponse(BaseModel):
    """Standard response for ops commands."""

    success: bool
    application_id: UUID
    action: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ─── Ops Read Responses ────────────────────────────────────────


class OpsApplicationDetail(BaseModel):
    """Full application detail for ops reconciliation."""

    application_id: UUID
    vendor_gstin: str
    anchor_gstin: str
    amount_requested: Decimal | None = None
    status: str
    current_gate: str | None = None
    workflow_id: str | None = None
    ops_hold: bool = False
    ops_flags: list[dict] = Field(default_factory=list)
    offer_data: dict | None = None
    amount_sanctioned: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OpsApplicationList(BaseModel):
    """List of active applications for reconciliation."""

    applications: list[OpsApplicationDetail]
    total: int


# ─── Vendor/Anchor Onboarding Requests ─────────────────────────


class VendorInviteRequest(BaseModel):
    """Ops invites a vendor (creates pending record, returns invite token)."""

    name: str
    gstin: str = Field(..., min_length=15, max_length=15)
    phone: str = Field(..., min_length=10, max_length=13)
    udyam_number: str | None = None
    invited_by: str


class VendorInviteResponse(BaseModel):
    """Response with invite token for the vendor."""

    vendor_id: UUID
    invite_token: str
    invite_link: str
    status: str = "invited"


class VendorRegisterRequest(BaseModel):
    """Vendor self-registration from PWA."""

    name: str
    gstin: str = Field(..., min_length=15, max_length=15)
    phone: str = Field(..., min_length=10, max_length=13)
    udyam_number: str | None = None
    udyam_category: str | None = None


class VendorRegisterResponse(BaseModel):
    """Response after vendor self-registration."""

    vendor_id: UUID
    status: str = "active"
    message: str


class VendorActivateRequest(BaseModel):
    """Complete an invited vendor's registration."""

    invite_token: str
    name: str | None = None
    udyam_number: str | None = None
    udyam_category: str | None = None


class AnchorOnboardRequest(BaseModel):
    """Ops onboards an anchor."""

    name: str
    gstin: str = Field(..., min_length=15, max_length=15)
    sector: str | None = None
    region: str | None = None
    onboarded_by: str


class AnchorOnboardResponse(BaseModel):
    """Response after anchor onboarding."""

    anchor_id: UUID
    status: str = "onboarded"
    message: str
