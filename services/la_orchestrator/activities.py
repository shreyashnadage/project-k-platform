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

logger = structlog.get_logger()


# ─── Activity Inputs (serializable dataclasses) ─────────────


@dataclass
class EvaluateDecisionInput:
    loan_application_id: str
    gate: str  # DecisionGate value
    ruleset_name: str  # e.g. "d0-kind1-gate"


@dataclass
class FetchAADataInput:
    loan_application_id: str


@dataclass
class SubmitToLenderInput:
    loan_application_id: str
    lender_ids: list[str]


# ─── Activities ─────────────────────────────────────────────


@activity.defn(name="evaluate_decision")
async def evaluate_decision(input: EvaluateDecisionInput) -> dict:
    """Evaluate a decision gate using the Zen Engine.

    Steps:
    1. Load the loan application + related data from DB
    2. Build the rule input context
    3. Evaluate via Zen Engine (in-process, sub-ms)
    4. Create a signed DecisionReceipt
    5. Emit LOAN_DECISION_EVALUATED event to Redpanda
    6. Return the outcome

    This is the ONLY place rules are evaluated — never in workflow code.
    """
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        gate=input.gate,
        ruleset=input.ruleset_name,
    )
    log.info("evaluating_decision_gate")

    # TODO: Implementation steps:
    # 1. Fetch loan application from Postgres
    # 2. Build context dict for the specific gate
    # 3. Call ZenDecisionEngine.evaluate(input.ruleset_name, context)
    # 4. Create DecisionReceipt via ReceiptSigner
    # 5. Emit trade event via Redpanda producer
    # 6. Update loan application status in DB

    # Placeholder — return structure matches what the workflow expects
    return {
        "outcome": "pass",
        "reason": "placeholder_not_implemented",
        "ruleset_hash": "placeholder",
        "receipt_id": "placeholder",
        "matched_lender_ids": [],  # populated only for D3
    }


@activity.defn(name="fetch_aa_data")
async def fetch_aa_data(input: FetchAADataInput) -> dict:
    """Fetch financial data via Account Aggregator (Setu/Perfios).

    Steps:
    1. Load the loan application to get vendor details
    2. Create AA consent request via Setu/Perfios API
    3. Wait for consent approval (heartbeat while waiting)
    4. Fetch financial data from FIPs
    5. Store decrypted data
    6. Emit LOAN_AA_DATA_RECEIVED event

    This activity may take minutes (user must approve consent on AA app).
    Use heartbeats to keep Temporal informed we're still alive.
    """
    log = logger.bind(loan_application_id=input.loan_application_id)
    log.info("fetching_aa_data")

    # TODO: Implementation via libs/aa_client
    # Key pattern: heartbeat while polling for consent approval
    # activity.heartbeat("waiting_for_consent")

    return {
        "data_received": True,
        "months_available": 0,
        "fips_responded": [],
    }


@activity.defn(name="submit_to_lender")
async def submit_to_lender(input: SubmitToLenderInput) -> dict:
    """Submit loan application to matched lender(s) via OCEN 4.0.

    Steps:
    1. Build OCEN CreateLoanApplications request
    2. Submit to each matched lender
    3. Await response (or register for OCEN callback)
    4. Emit LOAN_SUBMITTED_TO_LENDER and LOAN_OFFER_RECEIVED events

    Per OCEN: single soft-pull forwarded to lenders to protect borrower scores.
    """
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        lender_count=len(input.lender_ids),
    )
    log.info("submitting_to_lender")

    # TODO: Implementation via libs/ocen_client

    return {
        "offer_received": False,
        "offer": None,
    }
