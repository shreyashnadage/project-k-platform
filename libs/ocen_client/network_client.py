"""OCEN Network Client — orchestrates the full async loan application flow.

This is the top-level client that our Borrower Gateway uses to submit
loan applications to lenders via the OCEN network. It handles:
1. Token acquisition
2. Payload signing (JWS)
3. Registry lookup (find lenders in product network)
4. HTTP call to lender's createLoanRequest endpoint
5. Heartbeat event emission

Mirrors the LoanAgentServiceImpl from the OCEN AuthStarter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from libs.ocen_client.auth.config import OcenConfig
from libs.ocen_client.auth.token_service import OcenTokenService
from libs.ocen_client.heartbeat import HeartbeatEventType, OcenHeartbeatService
from libs.ocen_client.jws.signer import OcenJWSSigner
from libs.ocen_client.models.journey import (
    CreateLoanApplicationRequest,
    CreateLoanApplicationResponse,
    MetaData,
    OcenAckResponse,
    ProductData,
)
from libs.ocen_client.registry import OcenRegistryService

logger = structlog.get_logger()

OCEN_API_VERSION = "v4.0.0alpha"
CREATE_LOAN_REQUEST_PATH = f"/{OCEN_API_VERSION}/loanApplications/createLoanRequest"
CREATE_LOAN_RESPONSE_PATH = f"/{OCEN_API_VERSION}/loanApplications/createLoanResponse"


class OcenNetworkClient:
    """Orchestrates OCEN network transactions as a Loan Agent."""

    def __init__(self, config: OcenConfig | None = None) -> None:
        self._config = config or OcenConfig()
        self._token_service = OcenTokenService(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            token_url=self._config.token_url,
        )
        self._registry = OcenRegistryService(
            self._token_service, self._config.registry_base_url
        )
        self._heartbeat = OcenHeartbeatService(
            self._token_service, self._config.heartbeat_url
        )
        self._signer = OcenJWSSigner()  # Uses dev keypair; load from config in prod

    async def submit_loan_application(
        self, request: CreateLoanApplicationRequest
    ) -> list[OcenAckResponse]:
        """Submit a loan application to all lenders in the product network.

        Flow (mirrors OCEN AuthStarter LoanAgentServiceImpl):
        1. Get bearer token
        2. Sign the request body
        3. Look up lenders from the registry
        4. POST to each lender's createLoanRequest endpoint
        5. Emit heartbeat events
        """
        token = await self._token_service.get_bearer_token()
        request_json = request.model_dump_json(by_alias=True)
        signature = self._signer.sign(request_json)

        network = await self._registry.get_product_network_participants(
            request.product_data.product_network_id
        )

        ack_responses: list[OcenAckResponse] = []

        for lender in network.lenders:
            url = lender.base_url + CREATE_LOAN_REQUEST_PATH
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        url,
                        content=request_json,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {token}",
                            "x-jws-signature": signature,
                        },
                    )
                    resp.raise_for_status()
                    ack = OcenAckResponse.model_validate(resp.json())
                    ack_responses.append(ack)

                await self._emit_heartbeat(
                    HeartbeatEventType.CREATE_LOAN_APPLICATION_REQUEST,
                    request, 200, "Success", lender.id,
                )
            except Exception as e:
                logger.error(
                    "ocen_submit_failed", lender_id=lender.id, error=str(e)
                )
                await self._emit_heartbeat(
                    HeartbeatEventType.CREATE_LOAN_APPLICATION_REQUEST,
                    request, 500, str(e), lender.id,
                )

        return ack_responses

    async def handle_loan_response(
        self, response: CreateLoanApplicationResponse
    ) -> OcenAckResponse:
        """Handle async response from lender (createLoanResponse callback).

        Called when lender POSTs back to our createLoanResponse endpoint.
        """
        await self._emit_heartbeat(
            HeartbeatEventType.CREATE_LOAN_APPLICATIONS_RESPONSE_ACK,
            response, 200, "Success",
            response.metadata.originator_participant_id,
        )

        return OcenAckResponse(
            trace_id=response.metadata.trace_id,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def build_metadata(self, trace_id: str | None = None) -> MetaData:
        """Build OCEN MetaData for outgoing requests."""
        return MetaData(
            originatorOrgId=self._config.org_id,
            originatorParticipantId=self._config.participant_id,
            timestamp=datetime.now(UTC).isoformat(),
            traceId=trace_id or str(uuid.uuid4()),
            requestId=str(uuid.uuid4()),
        )

    def build_product_data(self) -> ProductData:
        """Build ProductData from config."""
        return ProductData(
            productId=self._config.product_id,
            productNetworkId=self._config.product_network_id,
        )

    async def _emit_heartbeat(
        self,
        event_type: HeartbeatEventType,
        request_or_response: Any,
        code: int,
        message: str,
        role_id: str,
    ) -> None:
        product_data = getattr(request_or_response, "product_data", None)
        product_id = product_data.product_id if product_data else ""
        product_network_id = product_data.product_network_id if product_data else ""

        loan_apps = getattr(request_or_response, "loan_applications", [])
        for app in loan_apps:
            await self._heartbeat.send_event(
                event_type=event_type,
                product_id=product_id,
                product_network_id=product_network_id,
                loan_application_id=app.loan_application_id,
                response_code=code,
                response_message=message,
                role_id=role_id,
            )
