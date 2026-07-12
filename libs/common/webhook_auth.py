"""Shared inbound HMAC signature verification for webhook-style endpoints.

Mirrors the outbound signing scheme in services/frappe_sync/webhook_client.py
(HMAC-SHA256 over the raw request body, hex-encoded) so the same secret and
algorithm are used on both ends of the platform<->Frappe webhook bridge.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_hmac_signature(secret: str, body: bytes, provided_signature: str | None) -> bool:
    """Constant-time verification of an HMAC-SHA256 signature over `body`."""
    if not secret or not provided_signature:
        return False
    expected = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided_signature)
