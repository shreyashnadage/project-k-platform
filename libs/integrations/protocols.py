"""Protocol definitions for all external integrations.

Real and mock implementations both conform to these protocols.
Calling code depends ONLY on these protocols, never on concrete implementations.
"""

from __future__ import annotations

from typing import Any, Protocol


class AAClient(Protocol):
    """Account Aggregator client — Setu/Perfios."""

    async def create_consent(
        self, vendor_gstin: str, purpose: str, duration_months: int
    ) -> ConsentResponse: ...

    async def check_consent_status(self, consent_id: str) -> ConsentStatus: ...

    async def fetch_financial_data(self, consent_id: str) -> FinancialData: ...


class OCENClient(Protocol):
    """OCEN 4.0 network client — loan submission to lenders."""

    async def submit_application(
        self, application_id: str, lender_ids: list[str], payload: dict[str, Any]
    ) -> SubmissionResponse: ...

    async def check_offer_status(self, submission_id: str) -> OfferStatus: ...

    async def accept_offer(self, offer_id: str) -> AcceptanceResponse: ...


class GSTClient(Protocol):
    """GST e-invoicing and IMS validation."""

    async def validate_irn(self, irn: str) -> IRNValidation: ...

    async def check_ims_status(self, irn: str, buyer_gstin: str) -> IMSStatus: ...

    async def validate_gstin(self, gstin: str) -> GSTINValidation: ...


class ConsentClient(Protocol):
    """DPDP consent ledger — grant/revoke/check consent status."""

    async def check_consent(
        self, data_principal_id: str, purposes: list[str]
    ) -> ConsentCheckResult: ...

    async def link_aa_consent(
        self, data_principal_id: str, aa_consent_id: str, loan_application_id: str
    ) -> None: ...


class UdyamClient(Protocol):
    """Udyam Registration verification — TSP-agnostic adapter.

    Verifies MSME registration status and retrieves enterprise details.
    Backed by any TSP: Gridlines, Surepass, Karza, etc.
    """

    async def verify(self, udyam_number: str) -> UdyamVerificationResult: ...


class LenderCallbackClient(Protocol):
    """Handles lender D4 underwriting callbacks."""

    async def register_webhook(self, application_id: str, callback_url: str) -> str: ...

    async def poll_decision(self, application_id: str) -> LenderDecision: ...


# ─── Response Types ────────────────────────────────────────────


class ConsentResponse:
    def __init__(self, consent_id: str, redirect_url: str, status: str = "pending") -> None:
        self.consent_id = consent_id
        self.redirect_url = redirect_url
        self.status = status


class ConsentStatus:
    def __init__(self, consent_id: str, status: str, approved_at: str | None = None) -> None:
        self.consent_id = consent_id
        self.status = status
        self.approved_at = approved_at


class FinancialData:
    def __init__(
        self,
        consent_id: str,
        months_available: int,
        bank_statements: list[dict[str, Any]] | None = None,
        gst_returns: list[dict[str, Any]] | None = None,
    ) -> None:
        self.consent_id = consent_id
        self.months_available = months_available
        self.bank_statements = bank_statements or []
        self.gst_returns = gst_returns or []


class SubmissionResponse:
    def __init__(
        self, submission_id: str, status: str, lender_acks: list[str] | None = None
    ) -> None:
        self.submission_id = submission_id
        self.status = status
        self.lender_acks = lender_acks or []


class OfferStatus:
    def __init__(
        self,
        submission_id: str,
        status: str,
        offers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.submission_id = submission_id
        self.status = status
        self.offers = offers or []


class AcceptanceResponse:
    def __init__(self, offer_id: str, status: str, disbursement_eta: str | None = None) -> None:
        self.offer_id = offer_id
        self.status = status
        self.disbursement_eta = disbursement_eta


class IRNValidation:
    def __init__(
        self,
        irn: str,
        valid: bool,
        invoice_date: str | None = None,
        seller_gstin: str | None = None,
    ) -> None:
        self.irn = irn
        self.valid = valid
        self.invoice_date = invoice_date
        self.seller_gstin = seller_gstin


class IMSStatus:
    def __init__(self, irn: str, status: str, action_date: str | None = None) -> None:
        self.irn = irn
        self.status = status
        self.action_date = action_date


class GSTINValidation:
    def __init__(
        self, gstin: str, valid: bool, trade_name: str | None = None, status: str = "Active"
    ) -> None:
        self.gstin = gstin
        self.valid = valid
        self.trade_name = trade_name
        self.status = status


class ConsentCheckResult:
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason


class UdyamVerificationResult:
    """Normalized Udyam verification response — TSP-agnostic."""

    def __init__(
        self,
        udyam_number: str,
        valid: bool,
        enterprise_name: str | None = None,
        enterprise_type: str | None = None,
        major_activity: str | None = None,
        organization_type: str | None = None,
        date_of_incorporation: str | None = None,
        date_of_commencement: str | None = None,
        date_of_udyam_registration: str | None = None,
        state: str | None = None,
        district: str | None = None,
        city: str | None = None,
        pincode: str | None = None,
        address: str | None = None,
        nic_codes: list[dict[str, str]] | None = None,
        owner_name: str | None = None,
        social_category: str | None = None,
        dic: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        self.udyam_number = udyam_number
        self.valid = valid
        self.enterprise_name = enterprise_name
        self.enterprise_type = enterprise_type
        self.major_activity = major_activity
        self.organization_type = organization_type
        self.date_of_incorporation = date_of_incorporation
        self.date_of_commencement = date_of_commencement
        self.date_of_udyam_registration = date_of_udyam_registration
        self.state = state
        self.district = district
        self.city = city
        self.pincode = pincode
        self.address = address
        self.nic_codes = nic_codes or []
        self.owner_name = owner_name
        self.social_category = social_category
        self.dic = dic
        self.raw_response = raw_response


class LenderDecision:
    def __init__(
        self,
        application_id: str,
        status: str,
        amount_sanctioned: str | None = None,
        interest_rate: str | None = None,
        tenure_days: int | None = None,
    ) -> None:
        self.application_id = application_id
        self.status = status
        self.amount_sanctioned = amount_sanctioned
        self.interest_rate = interest_rate
        self.tenure_days = tenure_days
