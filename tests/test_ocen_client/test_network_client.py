"""Tests for OCEN Network Client — mocked HTTP interactions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.ocen_client.auth.config import OcenConfig
from libs.ocen_client.models.journey import (
    CreateLoanApplicationRequest,
    LoanApplication,
    MetaData,
    ProductData,
)
from libs.ocen_client.models.registry import ParticipantDetail, ProductNetworkDetail
from libs.ocen_client.network_client import OcenNetworkClient


@pytest.fixture
def ocen_config() -> OcenConfig:
    return OcenConfig(
        client_id="test-client",
        client_secret="test-secret",
        token_url="https://auth.test/token",
        registry_base_url="https://registry.test",
        heartbeat_url="https://heartbeat.test/event",
        participant_id="LA-001",
        org_id="ORG-001",
        product_id="PROD-001",
        product_network_id="PN-001",
    )


@pytest.fixture
def sample_request() -> CreateLoanApplicationRequest:
    return CreateLoanApplicationRequest(
        metadata=MetaData(
            originatorOrgId="ORG-001",
            originatorParticipantId="LA-001",
            timestamp="2025-01-01T00:00:00Z",
            traceId="trace-1",
            requestId="req-1",
        ),
        product_data=ProductData(productId="PROD-001", productNetworkId="PN-001"),
        loan_applications=[
            LoanApplication(loan_application_id="APP-001"),
        ],
    )


class TestOcenNetworkClient:
    @pytest.mark.asyncio
    async def test_build_metadata(self, ocen_config: OcenConfig) -> None:
        client = OcenNetworkClient(config=ocen_config)
        meta = client.build_metadata(trace_id="test-trace")

        assert meta.originator_org_id == "ORG-001"
        assert meta.originator_participant_id == "LA-001"
        assert meta.trace_id == "test-trace"
        assert meta.request_id  # should be a UUID

    @pytest.mark.asyncio
    async def test_build_product_data(self, ocen_config: OcenConfig) -> None:
        client = OcenNetworkClient(config=ocen_config)
        pd = client.build_product_data()

        assert pd.product_id == "PROD-001"
        assert pd.product_network_id == "PN-001"

    @pytest.mark.asyncio
    async def test_submit_loan_application(
        self, ocen_config: OcenConfig, sample_request: CreateLoanApplicationRequest
    ) -> None:
        client = OcenNetworkClient(config=ocen_config)

        mock_network = ProductNetworkDetail(
            lenders=[
                ParticipantDetail(
                    id="LENDER-1",
                    participantRole="LENDER",
                    baseUrl="https://lender1.test",
                )
            ]
        )

        with (
            patch.object(
                client._token_service,
                "get_bearer_token",
                new_callable=AsyncMock,
                return_value="mock-token",
            ),
            patch.object(
                client._registry,
                "get_product_network_participants",
                new_callable=AsyncMock,
                return_value=mock_network,
            ),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
            patch.object(client._heartbeat, "send_event", new_callable=AsyncMock),
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "traceId": "trace-1",
                "timestamp": "2025-01-01T00:00:00Z",
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            acks = await client.submit_loan_application(sample_request)

        assert len(acks) == 1
        assert acks[0].trace_id == "trace-1"
