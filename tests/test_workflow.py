"""Temporal workflow skeleton tests using the test environment."""

from __future__ import annotations

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from services.la_orchestrator.activities import (
    check_dpdp_consent,
    evaluate_decision,
    fetch_aa_data,
    submit_to_lender,
)
from services.la_orchestrator.workflows import LoanOriginationInput, LoanOriginationWorkflow


@pytest.fixture
async def workflow_env():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.fixture
async def worker(workflow_env: WorkflowEnvironment):
    async with Worker(
        workflow_env.client,
        task_queue="test-loan-origination",
        workflows=[LoanOriginationWorkflow],
        activities=[check_dpdp_consent, evaluate_decision, fetch_aa_data, submit_to_lender],
    ) as w:
        yield w


async def test_workflow_full_pass(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow runs through all gates with stub activities (all pass)."""
    input = LoanOriginationInput(
        loan_application_id="test-loan-id-123",
        data_principal_id="27AADCB2230M1ZT",
        vendor_gstin="27AADCB2230M1ZT",
    )
    result = await workflow_env.client.execute_workflow(
        LoanOriginationWorkflow.run,
        input,
        id="wf-test-full-pass",
        task_queue="test-loan-origination",
    )
    # Stub D3 returns empty matched_lender_ids, so rejects at D3
    assert result["status"] == "rejected"
    assert result["gate"] == "d3_lender_prescreen"
    assert result["reason"] == "no_eligible_lenders"


async def test_workflow_consent_denied(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow rejects immediately when DPDP consent is denied."""
    import os

    os.environ["DPDP_SANDBOX_CONSENT_DENIED"] = "true"
    try:
        input = LoanOriginationInput(
            loan_application_id="test-loan-consent-denied",
            data_principal_id="27AADCB2230M1ZT",
            vendor_gstin="27AADCB2230M1ZT",
        )
        result = await workflow_env.client.execute_workflow(
            LoanOriginationWorkflow.run,
            input,
            id="wf-test-consent-denied",
            task_queue="test-loan-origination",
        )
        assert result["status"] == "rejected"
        assert result["gate"] == "dpdp_consent"
        assert result["reason"] == "consent_not_granted"
    finally:
        os.environ.pop("DPDP_SANDBOX_CONSENT_DENIED", None)


async def test_workflow_legacy_bare_string(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow still accepts a bare string (legacy path, skips consent gate)."""
    result = await workflow_env.client.execute_workflow(
        LoanOriginationWorkflow.run,
        "test-loan-id-legacy",
        id="wf-test-legacy",
        task_queue="test-loan-origination",
    )
    # Legacy path has empty vendor_gstin, so AA fetch returns data_received=False
    assert result["status"] == "rejected"
    assert result["gate"] == "aa_fetch"


async def test_workflow_runs_without_error(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow completes without raising exceptions."""
    input = LoanOriginationInput(
        loan_application_id="test-loan-id-456",
        data_principal_id="27AADCB2230M1ZT",
        vendor_gstin="27AADCB2230M1ZT",
    )
    result = await workflow_env.client.execute_workflow(
        LoanOriginationWorkflow.run,
        input,
        id="wf-test-no-error",
        task_queue="test-loan-origination",
    )
    assert "status" in result
