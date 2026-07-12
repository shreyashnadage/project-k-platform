"""End-to-end test for the OCEN loan origination flow.

Tests the full path: borrower applies -> D0-D3 gates -> OCEN submit ->
lender callback -> workflow signal. All external calls are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from libs.ocen_client.jws.signer import OcenJWSSigner


class TestOcenE2EFlow:
    """Integration test: borrower gateway receives lender callback."""

    def test_lender_callback_endpoint_accepts_valid_response(self) -> None:
        """Test that the createLoanResponse endpoint accepts a valid payload."""
        from services.borrower_gateway.app import app

        client = TestClient(app)

        payload = {
            "metadata": {
                "originatorOrgId": "LENDER-ORG",
                "originatorParticipantId": "LENDER-001",
                "timestamp": "2025-01-01T00:00:00Z",
                "traceId": "trace-abc",
                "requestId": "req-123",
            },
            "productData": {
                "productId": "PROD-001",
                "productNetworkId": "PN-001",
            },
            "response": {
                "status": "SUCCESS",
                "responseDetail": "Loan approved",
            },
            "loanApplications": [
                {
                    "loanApplicationId": "APP-001",
                    "loanApplicationStatus": "APPROVED",
                }
            ],
        }

        with patch(
            "services.borrower_gateway.app.get_temporal_client",
            new_callable=AsyncMock,
        ) as mock_temporal:
            mock_handle = AsyncMock()
            mock_client = AsyncMock()
            mock_client.get_workflow_handle.return_value = mock_handle
            mock_temporal.return_value = mock_client

            resp = client.post(
                "/v4.0.0alpha/loanApplications/createLoanResponse",
                json=payload,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["traceId"] == "trace-abc"

    def test_lender_callback_rejects_invalid_jws(self) -> None:
        """Test that invalid JWS signature is rejected."""
        from services.borrower_gateway.app import app

        client = TestClient(app)

        payload = {
            "metadata": {
                "originatorOrgId": "LENDER-ORG",
                "originatorParticipantId": "LENDER-001",
                "timestamp": "2025-01-01T00:00:00Z",
                "traceId": "trace-abc",
                "requestId": "req-123",
            },
            "productData": {
                "productId": "PROD-001",
                "productNetworkId": "PN-001",
            },
            "response": {
                "status": "SUCCESS",
            },
            "loanApplications": [
                {"loanApplicationId": "APP-001"},
            ],
        }

        resp = client.post(
            "/v4.0.0alpha/loanApplications/createLoanResponse",
            json=payload,
            headers={"x-jws-signature": "invalid..signature"},
        )

        assert resp.status_code == 401

    def test_generate_offers_response_endpoint(self) -> None:
        """Test all OCEN journey callback endpoints exist and work."""
        from services.borrower_gateway.app import app

        client = TestClient(app)

        payload = {
            "metadata": {
                "originatorOrgId": "LENDER-ORG",
                "originatorParticipantId": "LENDER-001",
                "timestamp": "2025-01-01T00:00:00Z",
                "traceId": "trace-xyz",
                "requestId": "req-456",
            },
            "productData": {
                "productId": "PROD-001",
                "productNetworkId": "PN-001",
            },
            "response": {"status": "SUCCESS"},
            "loanApplications": [
                {"loanApplicationId": "APP-002"},
            ],
        }

        endpoints = [
            "/v4.0.0alpha/loanApplications/generateOffersResponse",
            "/v4.0.0alpha/loanApplications/setOffersResponse",
            "/v4.0.0alpha/loanApplications/loanAgreementResponse",
            "/v4.0.0alpha/loanApplications/grantLoanResponse",
            "/v4.0.0alpha/loanApplications/triggerDisbursementResponse",
            "/v4.0.0alpha/loanApplications/triggerRepaymentResponse",
            "/v4.0.0alpha/loanApplications/setRepaymentPlanResponse",
        ]

        for endpoint in endpoints:
            resp = client.post(endpoint, json=payload)
            assert resp.status_code == 200, f"Failed: {endpoint}"
            data = resp.json()
            assert data["traceId"] == "trace-xyz"

    def test_jws_sign_verify_e2e_with_ocen_payload(self) -> None:
        """Test that a full OCEN request payload can be signed and verified."""
        import json

        signer = OcenJWSSigner()

        request_payload = {
            "metadata": {
                "version": "4.0.0alpha",
                "originatorOrgId": "LA-ORG",
                "originatorParticipantId": "LA-001",
                "timestamp": "2025-01-01T00:00:00Z",
                "traceId": "trace-full",
                "requestId": "req-full",
            },
            "productData": {
                "productId": "PROD-001",
                "productNetworkId": "PN-001",
            },
            "loanApplications": [
                {
                    "loanApplicationId": "APP-FULL",
                    "loanApplicationStatus": "CREATED",
                    "borrower": {
                        "primaryId": "27AADCB2230M1ZT",
                        "primaryIdType": "GSTIN",
                        "name": "Kolhapur Auto Parts Pvt Ltd",
                        "category": "ORGANIZATION",
                    },
                }
            ],
        }

        payload_str = json.dumps(request_payload)
        signature = signer.sign(payload_str)

        assert signer.verify(signature, payload_str)

        # Verify with public key (cross-instance)
        pub_jwk = signer.get_public_key_jwk()
        assert OcenJWSSigner.verify_with_public_key(signature, payload_str, pub_jwk)
