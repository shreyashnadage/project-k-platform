"""Sandbox lender callback client — simulates D4 underwriting decision."""

from __future__ import annotations

import asyncio

import structlog

from libs.integrations.protocols import LenderDecision
from sandbox.config import (
    SANDBOX_LENDER_AUTO_APPROVE,
    SANDBOX_LENDER_INTEREST_RATE,
    SANDBOX_LENDER_MAX_AMOUNT,
    SANDBOX_LENDER_TENURE_DAYS,
    SANDBOX_RESPONSE_DELAY_MS,
)

logger = structlog.get_logger()


class SandboxLenderClient:
    """Sandbox lender that auto-approves applications within limits."""

    def __init__(self, auto_approve: bool | None = None) -> None:
        self._auto_approve = (
            auto_approve if auto_approve is not None else SANDBOX_LENDER_AUTO_APPROVE
        )

    async def _simulate_delay(self) -> None:
        if SANDBOX_RESPONSE_DELAY_MS > 0:
            await asyncio.sleep(SANDBOX_RESPONSE_DELAY_MS / 1000)

    async def register_webhook(self, application_id: str, callback_url: str) -> str:
        await self._simulate_delay()
        logger.info("sandbox_webhook_registered", application_id=application_id)
        return f"sandbox-webhook-{application_id[:8]}"

    async def poll_decision(self, application_id: str) -> LenderDecision:
        await self._simulate_delay()
        if self._auto_approve:
            logger.info("sandbox_lender_approved", application_id=application_id)
            return LenderDecision(
                application_id=application_id,
                status="approved",
                amount_sanctioned=SANDBOX_LENDER_MAX_AMOUNT,
                interest_rate=SANDBOX_LENDER_INTEREST_RATE,
                tenure_days=SANDBOX_LENDER_TENURE_DAYS,
            )
        logger.info("sandbox_lender_rejected", application_id=application_id)
        return LenderDecision(
            application_id=application_id,
            status="rejected",
        )
