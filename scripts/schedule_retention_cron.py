"""Schedule the RetentionEnforcementWorkflow as a daily Temporal cron.

Usage:
    uv run python scripts/schedule_retention_cron.py [--dry-run]

This creates a Temporal schedule that runs RetentionEnforcementWorkflow
daily at 2:00 AM IST (20:30 UTC previous day).
"""

from __future__ import annotations

import asyncio
import os
import sys

from temporalio.client import Client


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "loan-origination")

    print(f"Connecting to Temporal at {address}...")
    client = await Client.connect(address, namespace=namespace)

    schedule_id = "dpdp-retention-daily"

    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleSpec,
    )

    from services.la_orchestrator.workflows import (
        RetentionEnforcementInput,
        RetentionEnforcementWorkflow,
    )

    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            RetentionEnforcementWorkflow.run,
            RetentionEnforcementInput(dry_run=dry_run),
            id="retention-enforcement-cron",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(
            cron_expressions=["0 20 * * *"],  # 20:30 UTC = 2:00 AM IST
        ),
    )

    if dry_run:
        print(f"[DRY RUN] Would create schedule '{schedule_id}' with cron '0 20 * * *'")
        print("  Workflow: RetentionEnforcementWorkflow")
        print(f"  Task queue: {task_queue}")
        print("  Input: RetentionEnforcementInput(dry_run=True)")
        return

    try:
        await client.create_schedule(schedule_id, schedule)
        print(f"Schedule '{schedule_id}' created successfully.")
        print("  Cron: daily at 2:00 AM IST (20:00 UTC)")
        print("  Workflow: RetentionEnforcementWorkflow")
        print(f"  Task queue: {task_queue}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"Schedule '{schedule_id}' already exists. Use Temporal UI to update.")
        else:
            raise


if __name__ == "__main__":
    asyncio.run(main())
