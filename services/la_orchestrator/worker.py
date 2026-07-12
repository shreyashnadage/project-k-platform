"""Temporal worker entrypoint for the LA orchestrator.

Registers workflows and activities, then runs the worker.
Usage: uv run python -m services.la_orchestrator.worker
"""

from __future__ import annotations

import asyncio

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from services.la_orchestrator.activities import (
    evaluate_decision,
    fetch_aa_data,
    submit_to_lender,
)
from services.la_orchestrator.workflows import LoanOriginationWorkflow

logger = structlog.get_logger()

TEMPORAL_ADDRESS = "localhost:7233"
TASK_QUEUE = "loan-origination"


async def main() -> None:
    logger.info("connecting_to_temporal", address=TEMPORAL_ADDRESS)
    client = await Client.connect(TEMPORAL_ADDRESS)

    logger.info("starting_worker", task_queue=TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[LoanOriginationWorkflow],
        activities=[
            evaluate_decision,
            fetch_aa_data,
            submit_to_lender,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
