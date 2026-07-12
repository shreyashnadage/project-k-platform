"""Loan origination workflow — the Temporal saga.

This workflow orchestrates the full origination pipeline:
  Loan Request → D0 → AA Fetch → D1 → D2 → D3 → OCEN Submit → Offer → Accept → Disburse

CRITICAL RULES (never violate):
1. Workflow code is DETERMINISTIC — no I/O, no randomness, no clocks.
2. All external calls, DB reads, rule evaluations go in ACTIVITIES.
3. Activities must be IDEMPOTENT (Temporal may retry them).
4. Rules are evaluated via the Zen Engine INSIDE activities, never in workflow code.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Activity stubs are imported for type hints only — the actual
# implementations live in activities.py and are registered on the worker.
with workflow.unsafe.imports_passed_through():
    from services.la_orchestrator.activities import (
        CheckDPDPConsentInput,
        DSRInput,
        EvaluateDecisionInput,
        FetchAADataInput,
        SubmitOcenLoanRequestInput,
        SubmitToLenderInput,
    )


# ─── Workflow Input / Output ────────────────────────────────


from dataclasses import dataclass


@dataclass
class LoanOriginationInput:
    """Structured input for the loan origination workflow."""

    loan_application_id: str
    data_principal_id: str = ""
    vendor_gstin: str = ""


@workflow.defn
class LoanOriginationWorkflow:
    """The main loan origination saga.

    Each step is a Temporal activity. If any gate fails, the workflow
    completes with a rejection — no saga compensation needed for
    pre-disbursement gates (read-only). Post-disbursement compensation
    (e.g. clawback) would be a separate workflow.
    """

    def __init__(self) -> None:
        self._lender_response: dict | None = None
        self._ops_hold: bool = False
        self._ops_hold_reason: str = ""

    @workflow.signal
    async def lender_response_received(self, response: dict) -> None:
        """Signal sent by the OCEN callback endpoint when lender responds."""
        self._lender_response = response

    @workflow.signal
    async def ops_hold_requested(self, reason: str) -> None:
        """Signal from ops to hold the application before OCEN submission."""
        self._ops_hold = True
        self._ops_hold_reason = reason

    @workflow.signal
    async def ops_hold_released(self) -> None:
        """Signal from ops to release a held application."""
        self._ops_hold = False
        self._ops_hold_reason = ""

    @workflow.run
    async def run(self, input: LoanOriginationInput | str) -> dict:
        """Execute the origination pipeline.

        Args:
            input: LoanOriginationInput or bare loan_application_id (legacy)

        Returns:
            Final status dict with outcome and metadata
        """
        # Support both new structured input and legacy bare string
        if isinstance(input, str):
            loan_application_id = input
            data_principal_id = ""
            vendor_gstin = ""
        else:
            loan_application_id = input.loan_application_id
            data_principal_id = input.data_principal_id
            vendor_gstin = input.vendor_gstin

        retry = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
            non_retryable_error_types=["DecisionGateFailError", "ValidationError"],
        )
        activity_timeout = timedelta(seconds=60)
        aa_timeout = timedelta(minutes=10)  # AA callback can take time

        # ── DPDP Consent Gate (hard block) ───────────────────
        if data_principal_id:
            consent_result = await workflow.execute_activity(
                "check_dpdp_consent",
                CheckDPDPConsentInput(
                    loan_application_id=loan_application_id,
                    data_principal_id=data_principal_id,
                    purposes=["loan_origination", "kind1_attestation"],
                ),
                start_to_close_timeout=activity_timeout,
                retry_policy=retry,
            )

            if not consent_result["allowed"]:
                return {
                    "status": "rejected",
                    "gate": "dpdp_consent",
                    "reason": consent_result.get("reason", "consent_not_granted"),
                }

        # ── D0: Kind 1 Gate ──────────────────────────────────
        d0_result = await workflow.execute_activity(
            "evaluate_decision",
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d0_kind1_gate",
                ruleset_name="d0-kind1-gate",
            ),
            start_to_close_timeout=activity_timeout,
            retry_policy=retry,
        )

        if d0_result["outcome"] == "fail":
            return {
                "status": "rejected",
                "gate": "d0_kind1_gate",
                "reason": d0_result.get("reason", "kind1_conditions_not_met"),
            }

        # ── AA Consent + Data Fetch ──────────────────────────
        aa_result = await workflow.execute_activity(
            "fetch_aa_data",
            FetchAADataInput(
                loan_application_id=loan_application_id,
                vendor_gstin=vendor_gstin,
                data_principal_id=data_principal_id,
            ),
            start_to_close_timeout=aa_timeout,
            retry_policy=RetryPolicy(maximum_attempts=2),
            heartbeat_timeout=timedelta(minutes=2),
        )

        if not aa_result["data_received"]:
            return {
                "status": "rejected",
                "gate": "aa_fetch",
                "reason": "aa_consent_denied_or_timeout",
            }

        # ── D1: Data Sufficiency Gate ────────────────────────
        d1_result = await workflow.execute_activity(
            "evaluate_decision",
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d1_data_sufficiency",
                ruleset_name="d1-data-sufficiency",
            ),
            start_to_close_timeout=activity_timeout,
            retry_policy=retry,
        )

        if d1_result["outcome"] == "fail":
            return {
                "status": "rejected",
                "gate": "d1_data_sufficiency",
                "reason": d1_result.get("reason", "insufficient_data"),
            }

        # ── D2: Derived Attributes + Flags (DDP function) ────
        await workflow.execute_activity(
            "evaluate_decision",
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d2_derived_attributes",
                ruleset_name="d2-derived-flags",
            ),
            start_to_close_timeout=activity_timeout,
            retry_policy=retry,
        )

        # D2 doesn't gate — it computes and flags.
        # Flags are advisory; the lender's D4 decides.

        # ── D3: Lender Pre-screen ────────────────────────────
        d3_result = await workflow.execute_activity(
            "evaluate_decision",
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d3_lender_prescreen",
                ruleset_name="d3-lender-prescreen",
            ),
            start_to_close_timeout=activity_timeout,
            retry_policy=retry,
        )

        matched_lenders = d3_result.get("matched_lender_ids", [])
        if not matched_lenders:
            return {
                "status": "rejected",
                "gate": "d3_lender_prescreen",
                "reason": "no_eligible_lenders",
            }

        # ── Ops Hold Check (between D3 and OCEN submit) ─────
        if self._ops_hold:
            try:
                await workflow.wait_condition(
                    lambda: not self._ops_hold,
                    timeout=timedelta(hours=72),
                )
            except TimeoutError:
                return {
                    "status": "rejected",
                    "gate": "ops_hold",
                    "reason": "ops_hold_expired",
                }

        # ── Submit to Lender(s) via OCEN ─────────────────────
        # Use the mock-based client for quick sync flow
        submit_result = await workflow.execute_activity(
            "submit_to_lender",
            SubmitToLenderInput(
                loan_application_id=loan_application_id,
                lender_ids=matched_lenders,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        # Also submit via OCEN network protocol (async — real lenders)
        await workflow.execute_activity(
            "submit_ocen_loan_request",
            SubmitOcenLoanRequestInput(
                loan_application_id=loan_application_id,
            ),
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        # ── Await Lender Decision (D4 — theirs, not ours) ────
        # In mock mode, submit_to_lender returns the response immediately.
        # In production, lender responds async via OCEN createLoanResponse
        # which signals this workflow via lender_response_received.

        if submit_result.get("offer_received"):
            return {
                "status": "offer_received",
                "offer": submit_result["offer"],
                "matched_lenders": matched_lenders,
            }

        # Wait for async lender signal (up to 24h in production)
        try:
            await workflow.wait_condition(
                lambda: self._lender_response is not None,
                timeout=timedelta(hours=24),
            )
        except TimeoutError:
            return {
                "status": "rejected",
                "gate": "d4_lender_underwriting",
                "reason": "lender_response_timeout",
            }

        if self._lender_response and self._lender_response.get("offer"):
            return {
                "status": "offer_received",
                "offer": self._lender_response["offer"],
                "matched_lenders": matched_lenders,
            }

        return {
            "status": "rejected",
            "gate": "d4_lender_underwriting",
            "reason": self._lender_response.get("reason", "lender_declined")
            if self._lender_response
            else "lender_declined",
        }

        # Post-offer steps (acceptance, e-sign, disbursement, repayment
        # tracking) will be added as the workflow matures. Each is an
        # activity with its own idempotency and timeout handling.


# ─── DPDP: Data Subject Rights Fulfillment Workflow ───────────


@dataclass
class DSRWorkflowInput:
    """Input for the DSR fulfillment workflow."""

    request_id: str
    data_principal_id: str
    right_type: str  # access, erasure, correction, grievance, nomination


@workflow.defn
class DSRFulfillmentWorkflow:
    """Fulfills Data Subject Rights requests per DPDP Act 2023 Section 11-14.

    Routes to the appropriate activity based on right_type.
    SLA: 72 hours per DPDP Board guidelines.
    """

    @workflow.run
    async def run(self, input: DSRWorkflowInput) -> dict:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
        )
        activity_timeout = timedelta(minutes=5)

        dsr_input = DSRInput(
            request_id=input.request_id,
            data_principal_id=input.data_principal_id,
            right_type=input.right_type,
        )

        if input.right_type == "access":
            result = await workflow.execute_activity(
                "execute_access_right",
                dsr_input,
                start_to_close_timeout=activity_timeout,
                retry_policy=retry,
            )
        elif input.right_type == "erasure":
            result = await workflow.execute_activity(
                "execute_erasure_right",
                dsr_input,
                start_to_close_timeout=activity_timeout,
                retry_policy=retry,
            )
        elif input.right_type == "correction":
            result = await workflow.execute_activity(
                "execute_correction_right",
                dsr_input,
                start_to_close_timeout=activity_timeout,
                retry_policy=retry,
            )
        else:
            result = {
                "status": "unsupported",
                "reason": f"right_type '{input.right_type}' not implemented",
            }

        return {
            "request_id": input.request_id,
            "right_type": input.right_type,
            "result": result,
        }


# ─── DPDP: Retention Enforcement Workflow (Cron) ──────────────


@dataclass
class RetentionEnforcementInput:
    """Input for the retention cron workflow."""

    dry_run: bool = False


@workflow.defn
class RetentionEnforcementWorkflow:
    """Enforces data retention policies from dpdp_config.yaml.

    Scheduled as a Temporal cron (daily at 2 AM IST).
    Walks each retention category and pseudonymizes/deletes expired records.
    """

    @workflow.run
    async def run(self, input: RetentionEnforcementInput) -> dict:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=120),
            maximum_attempts=3,
        )

        result = await workflow.execute_activity(
            "enforce_retention",
            input,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        return result


# ─── DPDP: Breach Detection Workflow ─────────────────────────


@dataclass
class BreachDetectionInput:
    """Input for breach detection — triggered by audit log patterns."""

    rule: str
    event_count: int
    window_minutes: int
    actor_id: str = ""
    details: dict | None = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = {}


@workflow.defn
class BreachDetectionWorkflow:
    """Handles a suspected data breach per DPDP Act Section 8(6).

    Triggered when audit log consumer detects suspicious patterns.
    Notifies DPBI within 72 hours and affected data principals.
    """

    @workflow.run
    async def run(self, input: BreachDetectionInput) -> dict:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        )

        detection_result = await workflow.execute_activity(
            "detect_breaches",
            input,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        if not detection_result.get("confirmed"):
            return {
                "rule": input.rule,
                "confirmed": False,
                "reason": detection_result.get("reason", "below_threshold"),
            }

        notification_result = await workflow.execute_activity(
            "notify_dpbi",
            input,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        principal_result = await workflow.execute_activity(
            "notify_affected_principals",
            input,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        return {
            "rule": input.rule,
            "confirmed": True,
            "dpbi_notified": notification_result.get("notified", False),
            "principals_notified": principal_result.get("count", 0),
        }
