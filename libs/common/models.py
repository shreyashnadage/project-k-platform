"""Core domain models for the OCEN platform.

These are the canonical Pydantic v2 models shared across all services.
Every service imports from here — never duplicate these definitions.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from dpdp_core.classification.field_meta import dpdp_field
from dpdp_core.classification.taxonomy import DPDPCategory, DPDPPurpose, DPDPTier
from dpdp_core.config import get_config as _get_dpdp_config
from pydantic import BaseModel, Field


def _retention_days(data_category: str) -> int:
    """Look up a retention period from dpdp_config.yaml's `retention:` list
    by data_category, resolved once at import time. This is the single
    source of truth for every dpdp_field(retention_days=...) call below —
    edit dpdp_config.yaml, not these call sites, to change a retention period.
    """
    for policy in _get_dpdp_config().retention:
        if policy.data_category == data_category:
            return int(policy.retention_days)
    raise KeyError(f"No dpdp_config.yaml retention policy for data_category={data_category!r}")


# Module-level constants — resolved once, referenced by every dpdp_field()
# call across libs/common/models.py, services/borrower_gateway/models.py,
# and services/borrower_gateway/ops_models.py.
RETENTION_LOAN_APPLICATION = _retention_days("loan_application")
RETENTION_VENDOR_CONTACT = _retention_days("vendor_contact")


def _required_consent_purposes() -> list[str]:
    """dpdp_config.yaml's consent.required_purposes list.

    Read directly from YAML (not via dpdp_core.config.get_config()) because
    the vendored dpdp-core package's DPDPConfig schema doesn't map the
    `consent:` section at all — a pre-existing gap in that dependency, not
    something this platform repo can extend. This is the single source of
    truth for every "purposes the platform requires consent for" check —
    previously re-typed as a literal list in 5 separate call sites.
    """
    import os

    import yaml

    config_path = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        purposes = raw.get("consent", {}).get("required_purposes")
        if purposes:
            return list(purposes)
    except FileNotFoundError:
        pass
    return ["loan_origination", "kind1_attestation"]


REQUIRED_CONSENT_PURPOSES = _required_consent_purposes()

# ─── Enums ──────────────────────────────────────────────────


class InvoiceIMSStatus(enum.StrEnum):
    """GST Invoice Management System acceptance status."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING = "pending"
    DEEMED_ACCEPTED = "deemed_accepted"  # No action taken — weaker signal


class LoanApplicationStatus(enum.StrEnum):
    """Loan lifecycle states (OCEN-aligned)."""

    CREATED = "created"
    KIND1_VALIDATED = "kind1_validated"
    AA_CONSENT_REQUESTED = "aa_consent_requested"
    AA_DATA_RECEIVED = "aa_data_received"
    DATA_SUFFICIENT = "data_sufficient"
    DERIVED_COMPUTED = "derived_computed"
    LENDER_MATCHED = "lender_matched"
    SUBMITTED_TO_LENDER = "submitted_to_lender"
    OFFER_RECEIVED = "offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    DISBURSED = "disbursed"
    REPAYING = "repaying"
    CLOSED = "closed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DecisionGate(enum.StrEnum):
    """The four decision gates we own (D0-D3). D4 is the lender's."""

    D0_KIND1_GATE = "d0_kind1_gate"
    D1_DATA_SUFFICIENCY = "d1_data_sufficiency"
    D2_DERIVED_ATTRIBUTES = "d2_derived_attributes"
    D3_LENDER_PRESCREEN = "d3_lender_prescreen"


class DecisionOutcome(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    FLAG = "flag"  # pass with warnings


class UdyamCategory(enum.StrEnum):
    """MSME Udyam registration categories. Only micro and small
    are covered by Section 43B(h)."""

    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"


# ─── Identity Models ───────────────────────────────────────


class GSTIN(BaseModel):
    """A validated GST Identification Number."""

    value: str = dpdp_field(
        category=DPDPCategory.FINANCIAL_IDENTIFIER,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.KIND1_ATTESTATION],
        retention_days=RETENTION_LOAN_APPLICATION,
        min_length=15,
        max_length=15,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
    )


class AnchorProfile(BaseModel):
    """An anchor (large buyer / corporate)."""

    id: UUID = Field(default_factory=uuid4)
    name: str = dpdp_field(
        category=DPDPCategory.NAME,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.OPS_MANAGEMENT],
        retention_days=RETENTION_LOAN_APPLICATION,
        default=...,
    )
    gstin: GSTIN
    sector: str | None = None
    region: str | None = None
    repayment_routing_active: bool = False
    onboarded_at: datetime | None = None


class VendorProfile(BaseModel):
    """A vendor (MSME supplier / potential borrower)."""

    id: UUID = Field(default_factory=uuid4)
    name: str = dpdp_field(
        category=DPDPCategory.NAME,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.OPS_MANAGEMENT],
        retention_days=RETENTION_LOAN_APPLICATION,
        default=...,
    )
    gstin: GSTIN
    udyam_number: str | None = dpdp_field(
        category=DPDPCategory.GOVERNMENT_ID,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION],
        retention_days=RETENTION_LOAN_APPLICATION,
        default=None,
    )
    udyam_category: UdyamCategory | None = None
    anchor_ids: list[UUID] = Field(default_factory=list)
    onboarded_at: datetime | None = None


# ─── Invoice & Attestation ─────────────────────────────────


class Invoice(BaseModel):
    """An invoice with e-invoicing and IMS attestation status."""

    id: UUID = Field(default_factory=uuid4)
    irn: str = dpdp_field(
        category=DPDPCategory.FINANCIAL_IDENTIFIER,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.KIND1_ATTESTATION, DPDPPurpose.LOAN_ORIGINATION],
        retention_days=RETENTION_LOAN_APPLICATION,
        min_length=64,
        max_length=64,
        description="Invoice Reference Number — 64-char SHA-256 hash",
    )
    anchor_gstin: GSTIN
    vendor_gstin: GSTIN
    invoice_number: str
    invoice_date: date
    due_date: date
    amount: Decimal = Field(..., gt=0)
    currency: str = "INR"
    ims_status: InvoiceIMSStatus = InvoiceIMSStatus.PENDING
    ims_checked_at: datetime | None = None
    irn_validated: bool = False
    irn_validated_at: datetime | None = None


class Kind1Attestation(BaseModel):
    """The combined attestation: valid IRN + IMS accepted + routing active.
    This is the structural proof that makes the receivable financeable."""

    invoice_id: UUID
    irn_valid: bool
    ims_accepted: bool  # True only for ACCEPTED, not DEEMED_ACCEPTED
    ims_status: InvoiceIMSStatus
    repayment_routing_active: bool
    is_kind1: bool = False  # True only if all three are True
    attested_at: datetime | None = None

    def model_post_init(self, __context: Any) -> None:
        self.is_kind1 = self.irn_valid and self.ims_accepted and self.repayment_routing_active


# ─── Loan Application ──────────────────────────────────────


class LoanApplication(BaseModel):
    """A loan application flowing through the origination pipeline."""

    id: UUID = Field(default_factory=uuid4)
    vendor_id: UUID
    anchor_id: UUID
    invoice_id: UUID
    requested_amount: Decimal
    requested_tenor_days: int
    status: LoanApplicationStatus = LoanApplicationStatus.CREATED
    kind1: Kind1Attestation | None = None
    matched_lender_ids: list[UUID] = Field(default_factory=list)
    selected_lender_id: UUID | None = None
    offer: LoanOffer | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LoanOffer(BaseModel):
    """An offer from a lender (OCEN CreateLoanApplicationsResponse)."""

    lender_id: UUID
    approved_amount: Decimal
    interest_rate_bps: int  # basis points
    tenor_days: int
    processing_fee: Decimal = Decimal("0")
    offer_valid_until: datetime
    kfs_url: str | None = None  # Key Fact Statement — RBI mandated


# ─── Decision Receipt (Audit Layer) ────────────────────────


class DecisionReceipt(BaseModel):
    """Signed, content-addressed record of a rule evaluation.
    Written to the Redpanda event stream and pinned to the application record.
    This is the DDP audit trail."""

    id: UUID = Field(default_factory=uuid4)
    loan_application_id: UUID
    gate: DecisionGate
    outcome: DecisionOutcome
    ruleset_hash: str = Field(..., description="SHA-256 of the canonical JDM ruleset JSON")
    input_hash: str = Field(..., description="SHA-256 of the canonical input JSON")
    output: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    engine_version: str = Field(..., description="GoRules Zen engine version")
    signature: str | None = Field(None, description="KMS/HSM signature over the receipt")
    chain_hash: str | None = Field(None, description="h_n = SHA-256(receipt ‖ h_{n-1})")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Derived Attributes (DDP Output) ───────────────────────


class DerivedAttributes(BaseModel):
    """The DDP-computed derived data package for a vendor/invoice.
    These are the attributes the Trust Graph computes and the DDP serves."""

    vendor_id: UUID
    as_of_date: date

    # Working capital metrics
    dso_days: Decimal | None = None  # Days Sales Outstanding
    dpo_days: Decimal | None = None  # Days Payable Outstanding
    dio_days: Decimal | None = None  # Days Inventory Outstanding
    ccc_days: Decimal | None = None  # Cash Conversion Cycle

    # Receivable quality
    receivable_concentration_top1_pct: Decimal | None = None
    receivable_concentration_top3_pct: Decimal | None = None
    dilution_rate_pct: Decimal | None = None

    # Anchor payment behaviour
    anchor_avg_payment_delay_days: Decimal | None = None
    anchor_payment_regularity_score: Decimal | None = None  # 0-1

    # GST-derived
    gst_filed_last_6m: int | None = None
    verified_annual_turnover: Decimal | None = None

    # Metadata
    ruleset_hash: str | None = None
    receipt_id: UUID | None = None


# ─── Lender Filter (for D3 pre-screen) ─────────────────────


class LenderFilter(BaseModel):
    """A lender's published coarse eligibility filters.
    We encode ONLY these — never the lender's internal underwriting."""

    lender_id: UUID
    lender_name: str
    min_ticket: Decimal = Decimal("50000")
    max_ticket: Decimal = Decimal("5000000")
    accepted_sectors: list[str] = Field(default_factory=list)
    accepted_regions: list[str] = Field(default_factory=list)
    max_tenor_days: int = 180
    min_udyam_category: UdyamCategory | None = UdyamCategory.MICRO
    max_anchor_concentration_pct: Decimal = Decimal("100")
    requires_gst_filed_last_6m: int = 0
    active: bool = True
