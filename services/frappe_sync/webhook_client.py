"""HMAC-signed webhook client for pushing events to Frappe."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import structlog

from .config import FRAPPE_API_KEY, FRAPPE_API_SECRET, FRAPPE_URL, WEBHOOK_SECRET

logger = structlog.get_logger()

MAX_RETRIES = 5
BACKOFF_BASE = 1.0


class FrappeWebhookClient:
    """Delivers signed webhooks to Frappe's ocen_ops app."""

    def __init__(
        self,
        frappe_url: str = FRAPPE_URL,
        api_key: str = FRAPPE_API_KEY,
        api_secret: str = FRAPPE_API_SECRET,
        webhook_secret: str = WEBHOOK_SECRET,
    ) -> None:
        self._frappe_url = frappe_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._webhook_secret = webhook_secret
        self._endpoint = f"{self._frappe_url}/api/method/ocen_ops.api.receive_platform_webhook"

    def _sign_payload(self, payload_bytes: bytes) -> str:
        """Generate HMAC-SHA256 signature for the webhook payload."""
        return hmac.HMAC(
            self._webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    def _build_headers(self, payload_bytes: bytes) -> dict[str, str]:
        signature = hmac.HMAC(
            self._webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Platform-Signature": signature,
        }
        if self._api_key and self._api_secret:
            headers["Authorization"] = f"token {self._api_key}:{self._api_secret}"
        return headers

    async def deliver(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Deliver a webhook with exponential retry."""
        body = json.dumps({"event_type": event_type, "payload": payload}, default=str)
        body_bytes = body.encode()
        headers = self._build_headers(body_bytes)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.post(
                        self._endpoint,
                        content=body_bytes,
                        headers=headers,
                    )
                    if response.status_code < 300:
                        logger.info(
                            "webhook_delivered",
                            event_type=event_type,
                            status=response.status_code,
                            attempt=attempt + 1,
                        )
                        return True

                    logger.warning(
                        "webhook_non_2xx",
                        event_type=event_type,
                        status=response.status_code,
                        attempt=attempt + 1,
                        body=response.text[:200],
                    )
                except httpx.RequestError as e:
                    logger.warning(
                        "webhook_request_error",
                        event_type=event_type,
                        error=str(e),
                        attempt=attempt + 1,
                    )

                if attempt < MAX_RETRIES - 1:
                    backoff = BACKOFF_BASE * (2**attempt)
                    await _async_sleep(backoff)

        logger.error(
            "webhook_delivery_failed",
            event_type=event_type,
            max_retries=MAX_RETRIES,
        )
        return False


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
