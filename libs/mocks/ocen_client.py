"""Mock OCEN 4.0 client — simulates lender submission and offer flow."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from libs.integrations.protocols import AcceptanceResponse, OfferStatus, SubmissionResponse

logger = structlog.get_logger()

MOCK_OFFER = {
    "lender_id": "lender-nbfc-001",
    "lender_name": "Partner NBFC (Mock)",
    "amount_offered": "450000.00",
    "interest_rate": "14.5",
    "tenure_days": 90,
    "processing_fee_pct": "1.5",
    "terms": {
        "prepayment_allowed": "true",
        "prepayment_penalty_pct": "2.0",
        "insurance_required": "false",
    },
}


class MockOCENClient:
    """Mock OCEN client returning a single pre-approved offer."""

    def __init__(self) -> None:
        self._submissions: dict[str, dict[str, Any]] = {}

    async def submit_application(
        self, application_id: str, lender_ids: list[str], payload: dict[str, Any]
    ) -> SubmissionResponse:
        submission_id = f"mock-sub-{uuid.uuid4().hex[:8]}"
        self._submissions[submission_id] = {
            "application_id": application_id,
            "lender_ids": lender_ids,
            "status": "offer_available",
        }
        logger.info(
            "mock_ocen_submitted",
            submission_id=submission_id,
            lender_count=len(lender_ids),
        )
        return SubmissionResponse(
            submission_id=submission_id,
            status="submitted",
            lender_acks=lender_ids,
        )

    async def check_offer_status(self, submission_id: str) -> OfferStatus:
        return OfferStatus(
            submission_id=submission_id,
            status="offer_available",
            offers=[MOCK_OFFER],
        )

    async def accept_offer(self, offer_id: str) -> AcceptanceResponse:
        logger.info("mock_ocen_offer_accepted", offer_id=offer_id)
        return AcceptanceResponse(
            offer_id=offer_id,
            status="accepted",
            disbursement_eta="2026-07-14T10:00:00Z",
        )
