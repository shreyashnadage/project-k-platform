"""OCEN Heartbeat service — analytics event reporting.

Every OCEN network transaction emits heartbeat events for monitoring
and audit. Events are fire-and-forget (async, non-blocking).
"""

from __future__ import annotations

import enum
import os
from datetime import UTC, datetime

import httpx
import structlog

from libs.ocen_client.auth.token_service import OcenTokenService  # noqa: TC001

logger = structlog.get_logger()

DEFAULT_HEARTBEAT_URL = "https://analytics-dev.ocen.network/ocen/v4/event"


class HeartbeatEventType(enum.StrEnum):
    """All OCEN heartbeat event types from the network specification."""

    CREATE_LOAN_APPLICATION_REQUEST = "CREATE_LOAN_APPLICATION_REQUEST"
    CREATE_LOAN_APPLICATION_REQUEST_ACK = "CREATE_LOAN_APPLICATION_REQUEST_ACK"
    CREATE_LOAN_APPLICATIONS_RESPONSE = "CREATE_LOAN_APPLICATIONS_RESPONSE"
    CREATE_LOAN_APPLICATIONS_RESPONSE_ACK = "CREATE_LOAN_APPLICATIONS_RESPONSE_ACK"
    CONSENT_HANDLE_REQUEST = "CONSENT_HANDLE_REQUEST"
    CONSENT_HANDLE_RESPONSE = "CONSENT_HANDLE_RESPONSE"
    GENERATE_OFFERS_REQUEST = "GENERATE_OFFERS_REQUEST"
    GENERATE_OFFERS_REQUEST_ACK = "GENERATE_OFFERS_REQUEST_ACK"
    GENERATE_OFFERS_RESPONSE = "GENERATE_OFFERS_RESPONSE"
    GENERATE_OFFERS_RESPONSE_ACK = "GENERATE_OFFERS_RESPONSE_ACK"
    SET_OFFERS_REQUEST = "SET_OFFERS_REQUEST"
    SET_OFFERS_REQUEST_ACK = "SET_OFFERS_REQUEST_ACK"
    SET_OFFERS_RESPONSE = "SET_OFFERS_RESPONSE"
    SET_OFFERS_RESPONSE_ACK = "SET_OFFERS_RESPONSE_ACK"
    LOAN_AGREEMENT_REQUEST = "LOAN_AGREEMENT_REQUEST"
    LOAN_AGREEMENT_REQUEST_ACK = "LOAN_AGREEMENT_REQUEST_ACK"
    LOAN_AGREEMENT_RESPONSE = "LOAN_AGREEMENT_RESPONSE"
    LOAN_AGREEMENT_RESPONSE_ACK = "LOAN_AGREEMENT_RESPONSE_ACK"
    GRANT_LOAN_REQUEST = "GRANT_LOAN_REQUEST"
    GRANT_LOAN_REQUEST_ACK = "GRANT_LOAN_REQUEST_ACK"
    GRANT_LOAN_RESPONSE = "GRANT_LOAN_RESPONSE"
    GRANT_LOAN_RESPONSE_ACK = "GRANT_LOAN_RESPONSE_ACK"
    TRIGGER_DISBURSEMENT_REQUEST = "TRIGGER_DISBURSEMENT_REQUEST"
    TRIGGER_DISBURSEMENT_REQUEST_ACK = "TRIGGER_DISBURSEMENT_REQUEST_ACK"
    TRIGGER_DISBURSEMENT_RESPONSE = "TRIGGER_DISBURSEMENT_RESPONSE"
    TRIGGER_DISBURSEMENT_RESPONSE_ACK = "TRIGGER_DISBURSEMENT_RESPONSE_ACK"
    TRIGGER_REPAYMENT_REQUEST = "TRIGGER_REPAYMENT_REQUEST"
    TRIGGER_REPAYMENT_RESPONSE = "TRIGGER_REPAYMENT_RESPONSE"
    SET_REPAYMENT_PLAN_REQUEST = "SET_REPAYMENT_PLAN_REQUEST"
    SET_REPAYMENT_PLAN_REQUEST_ACK = "SET_REPAYMENT_PLAN_REQUEST_ACK"


class OcenHeartbeatService:
    """Sends heartbeat analytics events to the OCEN network (fire-and-forget)."""

    def __init__(self, token_service: OcenTokenService, heartbeat_url: str | None = None) -> None:
        self._token_service = token_service
        self._url = heartbeat_url or os.environ.get(
            "OCEN_HEARTBEAT_URL", DEFAULT_HEARTBEAT_URL
        )

    async def send_event(
        self,
        event_type: HeartbeatEventType,
        product_id: str,
        product_network_id: str,
        loan_application_id: str,
        response_code: int,
        response_message: str,
        role_id: str,
    ) -> None:
        """Send a heartbeat event to the OCEN analytics endpoint."""
        event = {
            "eventType": event_type.value,
            "productId": product_id,
            "productNetworkId": product_network_id,
            "loanApplicationId": loan_application_id,
            "responseCode": response_code,
            "responseMessage": response_message,
            "roleId": role_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            token = await self._token_service.get_bearer_token()
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    self._url,
                    json={"events": [event]},
                    headers={"Authorization": f"Bearer {token}"},
                )
            logger.debug("heartbeat_sent", event_type=event_type.value)
        except Exception as e:
            logger.warning("heartbeat_failed", event_type=event_type.value, error=str(e))
