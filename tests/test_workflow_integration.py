"""Integration test for the LoanOriginationWorkflow using Temporal's test server."""

from __future__ import annotations

import asyncio

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from services.la_orchestrator.activities import (
    EvaluateDecisionInput,
    SubmitOcenLoanRequestInput,
    SubmitToLenderInput,
    fetch_aa_data,
)
from services.la_orchestrator.workflows import LoanOriginationWorkflow

# ─── Mock Activities ────────────────────────────────────────────


@activity.defn(name="evaluate_decision")
async def mock_evaluate_all_pass(input: EvaluateDecisionInput) -> dict:
    """All gates pass, D3 returns matched lenders."""
    return {
        "outcome": "pass",
        "reason": "mock_pass",
        "ruleset_hash": "mock-hash",
        "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
        "matched_lender_ids": ["lender-mock-1"],
    }


@activity.defn(name="evaluate_decision")
async def mock_evaluate_d0_fail(input: EvaluateDecisionInput) -> dict:
    """D0 fails, rest would pass."""
    if input.gate == "d0_kind1_gate":
        return {
            "outcome": "fail",
            "reason": "irn_invalid",
            "ruleset_hash": "mock-hash",
            "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
            "matched_lender_ids": [],
        }
    return {
        "outcome": "pass",
        "reason": "mock_pass",
        "ruleset_hash": "mock-hash",
        "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
        "matched_lender_ids": ["lender-mock-1"],
    }


@activity.defn(name="evaluate_decision")
async def mock_evaluate_no_lenders(input: EvaluateDecisionInput) -> dict:
    """All gates pass but D3 returns no matched lenders."""
    return {
        "outcome": "pass",
        "reason": "mock_pass",
        "ruleset_hash": "mock-hash",
        "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
        "matched_lender_ids": [],
    }


@activity.defn(name="submit_to_lender")
async def mock_submit_with_offer(input: SubmitToLenderInput) -> dict:
    return {
        "offer_received": True,
        "offer": {"rate": 12.5, "amount": 500000, "tenure_months": 3},
        "submission_id": "mock-sub-1",
    }


@activity.defn(name="submit_to_lender")
async def mock_submit_no_offer(input: SubmitToLenderInput) -> dict:
    return {"offer_received": False, "offer": None, "submission_id": "mock-sub-2"}


@activity.defn(name="submit_ocen_loan_request")
async def mock_ocen_submit(input: SubmitOcenLoanRequestInput) -> dict:
    return {"submitted": True, "ack_count": 1, "trace_ids": ["mock-trace-1"]}


@activity.defn(name="validate_gst")
async def mock_validate_gst(gstin: str) -> dict:
    return {"gstin": gstin, "valid": True, "trade_name": "Mock Trade"}


# ─── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def workflow_env():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


# ─── Tests ──────────────────────────────────────────────────────


class TestLoanOriginationWorkflow:
    """Full workflow test using Temporal's time-skipping test server."""

    @pytest.mark.asyncio
    async def test_full_origination_happy_path(
        self, workflow_env: WorkflowEnvironment
    ) -> None:
        """All gates pass, mock lender offers immediately."""
        async with Worker(
            workflow_env.client,
            task_queue="loan-origination",
            workflows=[LoanOriginationWorkflow],
            activities=[
                mock_evaluate_all_pass,
                fetch_aa_data,
                mock_submit_with_offer,
                mock_ocen_submit,
                mock_validate_gst,
            ],
        ):
            result = await workflow_env.client.execute_workflow(
                LoanOriginationWorkflow.run,
                "test-app-001",
                id="loan-origination-test-app-001",
                task_queue="loan-origination",
            )

        assert result["status"] == "offer_received"
        assert result["offer"]["rate"] == 12.5

    @pytest.mark.asyncio
    async def test_d0_gate_failure(
        self, workflow_env: WorkflowEnvironment
    ) -> None:
        """Workflow rejects when D0 (Kind 1) gate fails."""
        async with Worker(
            workflow_env.client,
            task_queue="loan-origination",
            workflows=[LoanOriginationWorkflow],
            activities=[
                mock_evaluate_d0_fail,
                fetch_aa_data,
                mock_submit_with_offer,
                mock_ocen_submit,
                mock_validate_gst,
            ],
        ):
            result = await workflow_env.client.execute_workflow(
                LoanOriginationWorkflow.run,
                "test-app-d0-fail",
                id="loan-origination-test-app-d0-fail",
                task_queue="loan-origination",
            )

        assert result["status"] == "rejected"
        assert result["gate"] == "d0_kind1_gate"
        assert result["reason"] == "irn_invalid"

    @pytest.mark.asyncio
    async def test_no_eligible_lenders(
        self, workflow_env: WorkflowEnvironment
    ) -> None:
        """Workflow rejects when D3 finds no eligible lenders."""
        async with Worker(
            workflow_env.client,
            task_queue="loan-origination",
            workflows=[LoanOriginationWorkflow],
            activities=[
                mock_evaluate_no_lenders,
                fetch_aa_data,
                mock_submit_with_offer,
                mock_ocen_submit,
                mock_validate_gst,
            ],
        ):
            result = await workflow_env.client.execute_workflow(
                LoanOriginationWorkflow.run,
                "test-app-no-lenders",
                id="loan-origination-test-app-no-lenders",
                task_queue="loan-origination",
            )

        assert result["status"] == "rejected"
        assert result["gate"] == "d3_lender_prescreen"
        assert result["reason"] == "no_eligible_lenders"

    @pytest.mark.asyncio
    async def test_lender_signal_after_no_immediate_offer(
        self, workflow_env: WorkflowEnvironment
    ) -> None:
        """Lender signal wakes the workflow when no immediate offer."""
        async with Worker(
            workflow_env.client,
            task_queue="loan-origination",
            workflows=[LoanOriginationWorkflow],
            activities=[
                mock_evaluate_all_pass,
                fetch_aa_data,
                mock_submit_no_offer,
                mock_ocen_submit,
                mock_validate_gst,
            ],
        ):
            handle = await workflow_env.client.start_workflow(
                LoanOriginationWorkflow.run,
                "test-app-signal",
                id="loan-origination-test-app-signal",
                task_queue="loan-origination",
            )

            await asyncio.sleep(2)

            await handle.signal(
                LoanOriginationWorkflow.lender_response_received,
                {
                    "offer": {"status": "SUCCESS", "rate": 11.0},
                    "loan_application_id": "test-app-signal",
                },
            )

            result = await handle.result()

        assert result["status"] == "offer_received"
        assert result["offer"]["status"] == "SUCCESS"
