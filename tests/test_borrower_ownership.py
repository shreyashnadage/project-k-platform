"""Tests for borrower ownership enforcement on /loans/apply and /loans/status.

BORROWER_AUTH_ENABLED is off by default (no Kratos/Hydra deployed yet) —
these tests monkeypatch it on and mock the borrower verifier, so the
ownership logic is verified independent of live CIAM infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from libs.auth.types import TokenClaims


def _make_claims(gstin: str) -> TokenClaims:
    return TokenClaims(subject="identity-123", raw={"gstin": gstin})


@pytest.fixture()
def client_with_auth_enabled(monkeypatch):
    from services.borrower_gateway import app as app_module

    monkeypatch.setattr(app_module, "BORROWER_AUTH_ENABLED", True)
    return TestClient(app_module.app, raise_server_exceptions=False), app_module


class TestLoansApplyOwnership:
    def test_missing_token_rejected(self, client_with_auth_enabled):
        client, _ = client_with_auth_enabled
        response = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000001",
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
        )
        assert response.status_code == 401

    def test_matching_gstin_allowed(self, client_with_auth_enabled, monkeypatch):
        client, app_module = client_with_auth_enabled
        mock_verifier = AsyncMock()
        mock_verifier.verify.return_value = _make_claims("27AADCB2230M1ZT")
        monkeypatch.setattr(app_module, "get_borrower_verifier", lambda: mock_verifier)

        response = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000001",
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200

    def test_mismatched_gstin_rejected(self, client_with_auth_enabled, monkeypatch):
        client, app_module = client_with_auth_enabled
        mock_verifier = AsyncMock()
        mock_verifier.verify.return_value = _make_claims("27AADCB2230M1ZT")
        monkeypatch.setattr(app_module, "get_borrower_verifier", lambda: mock_verifier)

        response = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000001",
                "vendor_gstin": "36AABCY9234H1Z5",  # different vendor's GSTIN
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403


class TestLoansStatusOwnership:
    def test_disabled_by_default_preserves_open_access(self):
        from services.borrower_gateway import app as app_module

        client = TestClient(app_module.app, raise_server_exceptions=False)
        create = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000002",
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
        )
        assert create.status_code == 200
        app_id = create.json()["application_id"]

        response = client.post("/loans/status", json={"application_id": app_id})
        assert response.status_code == 200

    def test_vendor_cannot_see_another_vendors_application(
        self, client_with_auth_enabled, monkeypatch
    ):
        client, app_module = client_with_auth_enabled

        # Vendor A creates an application (auth disabled momentarily for setup).
        monkeypatch.setattr(app_module, "BORROWER_AUTH_ENABLED", False)
        create = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000003",
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
        )
        app_id = create.json()["application_id"]

        # Vendor B (different GSTIN) tries to check its status.
        monkeypatch.setattr(app_module, "BORROWER_AUTH_ENABLED", True)
        mock_verifier = AsyncMock()
        mock_verifier.verify.return_value = _make_claims("36AABCY9234H1Z5")
        monkeypatch.setattr(app_module, "get_borrower_verifier", lambda: mock_verifier)

        response = client.post(
            "/loans/status",
            json={"application_id": app_id},
            headers={"Authorization": "Bearer vendor-b-token"},
        )
        assert response.status_code == 403

    def test_owning_vendor_can_see_own_application(
        self, client_with_auth_enabled, monkeypatch
    ):
        client, app_module = client_with_auth_enabled

        monkeypatch.setattr(app_module, "BORROWER_AUTH_ENABLED", False)
        create = client.post(
            "/loans/apply",
            json={
                "invoice_id": "00000000-0000-0000-0000-000000000004",
                "vendor_gstin": "27AADCB2230M1ZT",
                "anchor_gstin": "36AABCY9234H1Z5",
                "amount_requested": "50000.00",
            },
        )
        app_id = create.json()["application_id"]

        monkeypatch.setattr(app_module, "BORROWER_AUTH_ENABLED", True)
        mock_verifier = AsyncMock()
        mock_verifier.verify.return_value = _make_claims("27AADCB2230M1ZT")
        monkeypatch.setattr(app_module, "get_borrower_verifier", lambda: mock_verifier)

        response = client.post(
            "/loans/status",
            json={"application_id": app_id},
            headers={"Authorization": "Bearer vendor-a-token"},
        )
        assert response.status_code == 200
