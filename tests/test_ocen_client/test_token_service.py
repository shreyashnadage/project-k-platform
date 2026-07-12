"""Tests for OCEN OAuth2 token service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.ocen_client.auth.token_service import OcenTokenService


class TestOcenTokenService:
    @pytest.mark.asyncio
    async def test_get_bearer_token_calls_idp(self) -> None:
        service = OcenTokenService(
            client_id="test-id",
            client_secret="test-secret",
            token_url="https://auth.test/token",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "tok-123", "expires_in": 300}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            token = await service.get_bearer_token()

        assert token == "tok-123"

    @pytest.mark.asyncio
    async def test_caches_token(self) -> None:
        service = OcenTokenService(
            client_id="test-id",
            client_secret="test-secret",
            token_url="https://auth.test/token",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "tok-456", "expires_in": 300}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await service.get_bearer_token()
            await service.get_bearer_token()

        mock_post.assert_called_once()
