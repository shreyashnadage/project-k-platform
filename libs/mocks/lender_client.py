"""Mock lender callback client — simulates D4 underwriting decision."""

from __future__ import annotations

import structlog

from libs.integrations.protocols import LenderDecision

logger = structlog.get_logger()


class MockLenderCallbackClient:
    """Mock lender that auto-approves applications within limits."""

    def __init__(
        self,
        auto_approve: bool = True,
        max_amount: str = "1000000.00",
        interest_rate: str = "14.5",
        tenure_days: int = 90,
    ) -> None:
        self._auto_approve = auto_approve
        self._max_amount = max_amount
        self._interest_rate = interest_rate
        self._tenure_days = tenure_days

    async def register_webhook(self, application_id: str, callback_url: str) -> str:
        logger.info("mock_webhook_registered", application_id=application_id)
        return f"mock-webhook-{application_id[:8]}"

    async def poll_decision(self, application_id: str) -> LenderDecision:
        if self._auto_approve:
            logger.info("mock_lender_approved", application_id=application_id)
            return LenderDecision(
                application_id=application_id,
                status="approved",
                amount_sanctioned=self._max_amount,
                interest_rate=self._interest_rate,
                tenure_days=self._tenure_days,
            )
        logger.info("mock_lender_rejected", application_id=application_id)
        return LenderDecision(
            application_id=application_id,
            status="rejected",
        )
