"""OAuth2 token service for OCEN network authentication.

Obtains bearer tokens via client_credentials grant from the OCEN Identity Provider
(Keycloak at auth.ocen.network). Tokens are used for:
1. Registry API calls (participant/product-network discovery)
2. Heartbeat/analytics event submission
3. Inter-participant API calls (Authorization header)
"""

from __future__ import annotations

import os
import time

import httpx
import structlog

logger = structlog.get_logger()

DEFAULT_TOKEN_URL = "https://auth.ocen.network/realms/dev/protocol/openid-connect/token"


class OcenTokenService:
    """Manages OAuth2 bearer tokens for OCEN network calls."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        token_url: str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("OCEN_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("OCEN_CLIENT_SECRET", "")
        self._token_url = token_url or os.environ.get("OCEN_TOKEN_URL", DEFAULT_TOKEN_URL)
        self._cached_token: str | None = None
        self._token_expiry: float = 0

    async def get_bearer_token(self) -> str:
        """Get a valid bearer token, refreshing if expired."""
        if self._cached_token and time.time() < self._token_expiry:
            return self._cached_token

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        self._cached_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 300)
        self._token_expiry = time.time() + expires_in - 30  # refresh 30s early

        logger.info("ocen_token_acquired", expires_in=expires_in)
        return self._cached_token
