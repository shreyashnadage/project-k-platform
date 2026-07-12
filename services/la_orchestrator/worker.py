"""Temporal worker entrypoint for the LA orchestrator.

Registers workflows and activities, then runs the worker.
Usage: uv run python -m services.la_orchestrator.worker
"""

from __future__ import annotations

import asyncio
import os

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from services.la_orchestrator.activities import (
    check_dpdp_consent,
    evaluate_decision,
    execute_access_right,
    execute_correction_right,
    execute_erasure_right,
    fetch_aa_data,
    submit_ocen_loan_request,
    submit_to_lender,
    validate_gst,
)
from services.la_orchestrator.workflows import DSRFulfillmentWorkflow, LoanOriginationWorkflow

logger = structlog.get_logger()

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "loan-origination")


async def main() -> None:
    logger.info("connecting_to_temporal", address=TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)

    logger.info("starting_worker", task_queue=TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[LoanOriginationWorkflow, DSRFulfillmentWorkflow],
        activities=[
            check_dpdp_consent,
            evaluate_decision,
            execute_access_right,
            execute_correction_right,
            execute_erasure_right,
            fetch_aa_data,
            submit_to_lender,
            submit_ocen_loan_request,
            validate_gst,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
