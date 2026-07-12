"""Tests for OCEN JWS detached signature implementation."""

from __future__ import annotations

import json

from libs.ocen_client.jws.signer import OcenJWSSigner


class TestOcenJWSSigner:
    """Test JWS sign/verify roundtrip and detached format."""

    def test_sign_produces_detached_format(self) -> None:
        signer = OcenJWSSigner()
        payload = '{"test": "data"}'
        signature = signer.sign(payload)

        parts = signature.split(".")
        assert len(parts) == 3
        assert parts[1] == ""  # detached — empty payload section

    def test_sign_verify_roundtrip(self) -> None:
        signer = OcenJWSSigner()
        payload = '{"loanApplicationId": "abc-123", "amount": 50000}'
        signature = signer.sign(payload)

        assert signer.verify(signature, payload) is True

    def test_verify_fails_on_tampered_payload(self) -> None:
        signer = OcenJWSSigner()
        payload = '{"amount": 50000}'
        signature = signer.sign(payload)

        tampered = '{"amount": 99999}'
        assert signer.verify(signature, tampered) is False

    def test_verify_fails_on_invalid_signature(self) -> None:
        signer = OcenJWSSigner()
        assert signer.verify("invalid", "payload") is False
        assert signer.verify("a.b", "payload") is False

    def test_cross_instance_verify_with_public_key(self) -> None:
        signer = OcenJWSSigner()
        payload = '{"borrower": "vendor-1"}'
        signature = signer.sign(payload)
        public_key_jwk = signer.get_public_key_jwk()

        assert OcenJWSSigner.verify_with_public_key(signature, payload, public_key_jwk) is True

    def test_get_public_key_jwk_format(self) -> None:
        signer = OcenJWSSigner()
        jwk = json.loads(signer.get_public_key_jwk())

        assert jwk["kty"] == "RSA"
        assert jwk["alg"] == "RS256"
        assert jwk["use"] == "sig"
        assert "n" in jwk
        assert "e" in jwk
        assert "kid" in jwk
