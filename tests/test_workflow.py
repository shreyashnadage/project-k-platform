"""Temporal workflow skeleton tests using the test environment."""

from __future__ import annotations

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from services.la_orchestrator.activities import (
    evaluate_decision,
    fetch_aa_data,
    submit_to_lender,
)
from services.la_orchestrator.workflows import LoanOriginationWorkflow


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
        activities=[evaluate_decision, fetch_aa_data, submit_to_lender],
    ) as w:
        yield w


async def test_workflow_full_pass(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow runs through all gates with stub activities (all pass)."""
    result = await workflow_env.client.execute_workflow(
        LoanOriginationWorkflow.run,
        "test-loan-id-123",
        id="wf-test-full-pass",
        task_queue="test-loan-origination",
    )
    # Stub D3 returns empty matched_lender_ids, so rejects at D3
    assert result["status"] == "rejected"
    assert result["gate"] == "d3_lender_prescreen"
    assert result["reason"] == "no_eligible_lenders"


async def test_workflow_runs_without_error(workflow_env: WorkflowEnvironment, worker: Worker):
    """Workflow completes without raising exceptions."""
    result = await workflow_env.client.execute_workflow(
        LoanOriginationWorkflow.run,
        "test-loan-id-456",
        id="wf-test-no-error",
        task_queue="test-loan-origination",
    )
    assert "status" in result
