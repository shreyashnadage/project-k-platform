"""Temporal activities for the loan origination workflow.

Activities are where ALL non-deterministic work happens:
- Rule evaluation (Zen Engine, in-process)
- AA data fetch (Setu/Perfios, network call)
- OCEN submission (network call)
- DB reads/writes
- Event emission to Redpanda

Each activity MUST be idempotent — Temporal may retry on failure.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from temporalio import activity

from libs.integrations.factory import (
    get_aa_client,
    get_gst_client,
    get_ocen_client,
    get_ocen_network_client,
)
from libs.ocen_client.models.journey import (
    Borrower,
    CreateLoanApplicationRequest,
)
from libs.ocen_client.models.journey import (
    LoanApplication as OcenLoanApplication,
)
from libs.zen_rules.engine import ZenDecisionEngine

logger = structlog.get_logger()

_zen_engine: ZenDecisionEngine | None = None


def get_zen_engine() -> ZenDecisionEngine:
    global _zen_engine
    if _zen_engine is None:
        _zen_engine = ZenDecisionEngine("rules/")
    return _zen_engine


# ─── Activity Inputs (serializable dataclasses) ─────────────


@dataclass
class EvaluateDecisionInput:
    loan_application_id: str
    gate: str
    ruleset_name: str
    context: dict | None = None


@dataclass
class FetchAADataInput:
    loan_application_id: str
    vendor_gstin: str = ""


@dataclass
class SubmitToLenderInput:
    loan_application_id: str
    lender_ids: list[str] | None = None

    def __post_init__(self) -> None:
        if self.lender_ids is None:
            self.lender_ids = []


# ─── Activities ─────────────────────────────────────────────


@activity.defn(name="evaluate_decision")
async def evaluate_decision(input: EvaluateDecisionInput) -> dict:
    """Evaluate a decision gate using the Zen Engine."""
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        gate=input.gate,
        ruleset=input.ruleset_name,
    )
    log.info("evaluating_decision_gate")

    if input.context and input.ruleset_name in get_zen_engine().loaded_rulesets:
        result = get_zen_engine().evaluate(input.ruleset_name, input.context)
        return {
            "outcome": result.output.get("outcome", "pass"),
            "reason": result.output.get("reason", "evaluated"),
            "ruleset_hash": result.ruleset_hash,
            "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
            "matched_lender_ids": result.output.get("matched_lender_ids", []),
        }

    return {
        "outcome": "pass",
        "reason": "no_ruleset_or_context",
        "ruleset_hash": "none",
        "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
        "matched_lender_ids": [],
    }


@activity.defn(name="fetch_aa_data")
async def fetch_aa_data(input: FetchAADataInput) -> dict:
    """Fetch financial data via Account Aggregator (mocked or real)."""
    log = logger.bind(loan_application_id=input.loan_application_id)
    log.info("fetching_aa_data")

    aa_client = get_aa_client()
    consent = await aa_client.create_consent(
        vendor_gstin=input.vendor_gstin or "27AADCB2230M1ZT",
        purpose="loan_origination",
        duration_months=12,
    )

    status = await aa_client.check_consent_status(consent.consent_id)
    if status.status != "approved":
        return {"data_received": False, "months_available": 0, "fips_responded": []}

    data = await aa_client.fetch_financial_data(consent.consent_id)

    return {
        "data_received": True,
        "months_available": data.months_available,
        "fips_responded": [s.get("bank_name", "unknown") for s in data.bank_statements],
        "gst_returns_count": len(data.gst_returns),
    }


@activity.defn(name="submit_to_lender")
async def submit_to_lender(input: SubmitToLenderInput) -> dict:
    """Submit loan application to matched lender(s) via OCEN (mocked or real)."""
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        lender_count=len(input.lender_ids or []),
    )
    log.info("submitting_to_lender")

    ocen_client = get_ocen_client()
    submission = await ocen_client.submit_application(
        application_id=input.loan_application_id,
        lender_ids=input.lender_ids or [],
        payload={"application_id": input.loan_application_id},
    )

    offer_status = await ocen_client.check_offer_status(submission.submission_id)

    if offer_status.offers:
        return {
            "offer_received": True,
            "offer": offer_status.offers[0],
            "submission_id": submission.submission_id,
        }

    return {"offer_received": False, "offer": None, "submission_id": submission.submission_id}


@activity.defn(name="validate_gst")
async def validate_gst(gstin: str) -> dict:
    """Validate a GSTIN via GST portal (mocked or real)."""
    gst_client = get_gst_client()
    result = await gst_client.validate_gstin(gstin)
    return {"gstin": result.gstin, "valid": result.valid, "trade_name": result.trade_name}


# ─── OCEN Network Protocol Activities ─────────────────────────


@dataclass
class SubmitOcenLoanRequestInput:
    loan_application_id: str
    borrower_gstin: str = ""
    borrower_name: str = ""
    requested_amount: float = 0.0
    tenure_months: int = 3


@activity.defn(name="submit_ocen_loan_request")
async def submit_ocen_loan_request(input: SubmitOcenLoanRequestInput) -> dict:
    """Submit loan application to lenders via OCEN 4.0 network protocol.

    Builds a CreateLoanApplicationRequest with proper MetaData, signs it,
    and POSTs to all lenders in the product network.
    Returns ACK trace IDs — actual decisions arrive asynchronously.
    """
    log = logger.bind(loan_application_id=input.loan_application_id)
    log.info("submitting_ocen_loan_request")

    network_client = get_ocen_network_client()
    metadata = network_client.build_metadata()
    product_data = network_client.build_product_data()

    request = CreateLoanApplicationRequest(
        metadata=metadata,
        product_data=product_data,
        loan_applications=[
            OcenLoanApplication(
                loan_application_id=input.loan_application_id,
                borrower=Borrower(
                    primaryId=input.borrower_gstin or "UNKNOWN",
                    primary_id_type="GSTIN",
                    name=input.borrower_name,
                ),
            ),
        ],
    )

    acks = await network_client.submit_loan_application(request)

    return {
        "submitted": True,
        "ack_count": len(acks),
        "trace_ids": [ack.trace_id for ack in acks],
    }
