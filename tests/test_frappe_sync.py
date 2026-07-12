"""Tests for Frappe Sync webhook client and consumer config."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest


class TestWebhookClient:
    def test_hmac_signature_generation(self):
        secret = "test-secret"
        payload = json.dumps({"event_type": "loan.application_created", "payload": {}}).encode()
        expected = hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert len(expected) == 64

    def test_build_headers_includes_signature(self):
        from services.frappe_sync.webhook_client import FrappeWebhookClient

        client = FrappeWebhookClient(
            frappe_url="http://localhost:8080",
            api_key="test-key",
            api_secret="test-secret",
            webhook_secret="webhook-secret",
        )
        payload = b'{"event_type": "test", "payload": {}}'
        headers = client._build_headers(payload)

        assert "X-Platform-Signature" in headers
        assert "Authorization" in headers
        assert headers["Authorization"] == "token test-key:test-secret"
        assert headers["Content-Type"] == "application/json"

    def test_signature_is_valid_hmac(self):
        from services.frappe_sync.webhook_client import FrappeWebhookClient

        secret = "my-webhook-secret"
        client = FrappeWebhookClient(
            frappe_url="http://localhost:8080",
            api_key="",
            api_secret="",
            webhook_secret=secret,
        )
        payload = b'{"event_type": "loan.disbursed", "payload": {"amount": "150000"}}'
        headers = client._build_headers(payload)

        expected_sig = hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert headers["X-Platform-Signature"] == expected_sig


class TestConsumerConfig:
    def test_events_to_forward_includes_loan_events(self):
        from services.frappe_sync.config import EVENTS_TO_FORWARD

        assert "loan.application_created" in EVENTS_TO_FORWARD
        assert "loan.offer_received" in EVENTS_TO_FORWARD
        assert "loan.disbursed" in EVENTS_TO_FORWARD
        assert "loan.closed" in EVENTS_TO_FORWARD

    def test_events_to_forward_includes_ops_events(self):
        from services.frappe_sync.config import EVENTS_TO_FORWARD

        assert "ops.hold_applied" in EVENTS_TO_FORWARD
        assert "ops.hold_released" in EVENTS_TO_FORWARD
        assert "ops.escalated" in EVENTS_TO_FORWARD

    def test_events_to_forward_includes_onboarding_events(self):
        from services.frappe_sync.config import EVENTS_TO_FORWARD

        assert "vendor.onboarded" in EVENTS_TO_FORWARD
        assert "vendor.invited" in EVENTS_TO_FORWARD
        assert "anchor.onboarded" in EVENTS_TO_FORWARD
