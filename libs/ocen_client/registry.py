"""OCEN Registry service — participant and product network discovery.

Mirrors the RegistryServiceImpl from the OCEN AuthStarter.
"""

from __future__ import annotations

import os

import httpx
import structlog

from libs.ocen_client.auth.token_service import OcenTokenService  # noqa: TC001
from libs.ocen_client.models.registry import ParticipantDetail, ProductNetworkDetail

logger = structlog.get_logger()

DEFAULT_REGISTRY_URL = "https://dev.ocen.network/service"


class OcenRegistryService:
    """Queries the OCEN Registry for participant details and product networks."""

    def __init__(
        self,
        token_service: OcenTokenService,
        registry_base_url: str | None = None,
    ) -> None:
        self._token_service = token_service
        self._base_url = registry_base_url or os.environ.get(
            "OCEN_REGISTRY_BASE_URL", DEFAULT_REGISTRY_URL
        )

    async def get_participant_detail(self, participant_id: str) -> ParticipantDetail:
        """Fetch participant role details by participant ID."""
        token = await self._token_service.get_bearer_token()
        url = f"{self._base_url}/participant-roles/{participant_id}"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()

        return ParticipantDetail.model_validate(response.json())

    async def get_product_network_participants(
        self, product_network_id: str
    ) -> ProductNetworkDetail:
        """Fetch all participants (loan agents + lenders) in a product network."""
        token = await self._token_service.get_bearer_token()
        url = f"{self._base_url}/product-networks/{product_network_id}/participants"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()

        return ProductNetworkDetail.model_validate(response.json())
