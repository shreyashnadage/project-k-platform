"""JWS detached signature implementation (RFC 7797).

OCEN uses RSA-SHA256 detached signatures:
- Request body is signed but NOT included in the JWS token
- Signature is sent in the `x-jws-signature` header
- Verifier reconstructs by combining header + payload + signature

This is the Python equivalent of the Java JWSSigner in the OCEN AuthStarter.
"""

from __future__ import annotations

import base64
import json

import structlog
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey  # noqa: TC002

logger = structlog.get_logger()


class OcenJWSSigner:
    """Signs request/response bodies using RFC 7797 detached JWS (RSA-SHA256)."""

    def __init__(self, jwk_keyset_json: str | None = None) -> None:
        """Initialize with a JWK keyset JSON string.

        If None, generates a new keypair (for development/testing).
        """
        if jwk_keyset_json:
            self._private_key, self._public_key, self._kid = self._load_jwk(jwk_keyset_json)
        else:
            self._private_key, self._public_key, self._kid = self._generate_keypair()

    def sign(self, payload: str | bytes) -> str:
        """Generate a detached JWS signature for the given payload.

        Returns the compact serialization with empty payload section:
        <header>..<signature>
        """
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        header = {
            "alg": "RS256",
            "kid": self._kid,
            "b64": False,
            "crit": ["b64"],
        }
        header_b64 = _base64url_encode(json.dumps(header).encode())

        signing_input = header_b64.encode() + b"." + payload
        signature = self._private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        signature_b64 = _base64url_encode(signature)

        return f"{header_b64}..{signature_b64}"

    def verify(self, detached_signature: str, payload: str | bytes) -> bool:
        """Verify a detached JWS signature against the payload."""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        parts = detached_signature.split(".")
        if len(parts) != 3:
            return False

        header_b64 = parts[0]
        signature_b64 = parts[2]

        signing_input = header_b64.encode() + b"." + payload
        signature = _base64url_decode(signature_b64)

        try:
            self._public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def get_public_key_jwk(self) -> str:
        """Get the public key in JWK JSON format (for registry registration)."""
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers  # noqa: TC002

        pub_numbers: RSAPublicNumbers = self._public_key.public_numbers()
        n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, "big")
        e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, "big")

        jwk = {
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "kid": self._kid,
            "n": _base64url_encode(n_bytes),
            "e": _base64url_encode(e_bytes),
        }
        return json.dumps(jwk)

    @staticmethod
    def verify_with_public_key(
        detached_signature: str, payload: str | bytes, public_key_jwk: str
    ) -> bool:
        """Verify using a counterpart's public key (fetched from registry)."""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        parts = detached_signature.split(".")
        if len(parts) != 3:
            return False

        header_b64 = parts[0]
        signature_b64 = parts[2]

        jwk_data = json.loads(public_key_jwk)
        n = int.from_bytes(_base64url_decode(jwk_data["n"]), "big")
        e = int.from_bytes(_base64url_decode(jwk_data["e"]), "big")

        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

        pub_key = RSAPublicNumbers(e, n).public_key()

        signing_input = header_b64.encode() + b"." + payload
        signature = _base64url_decode(signature_b64)

        try:
            pub_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def _load_jwk(self, jwk_json: str) -> tuple[RSAPrivateKey, RSAPublicKey, str]:
        """Load RSA keypair from JWK JSON (same format as OCEN AuthStarter)."""
        keyset = json.loads(jwk_json)
        key_data = keyset["keys"][0] if "keys" in keyset else keyset

        kid = key_data.get("kid", "ocen-key-1")

        n = int.from_bytes(_base64url_decode(key_data["n"]), "big")
        e = int.from_bytes(_base64url_decode(key_data["e"]), "big")
        d = int.from_bytes(_base64url_decode(key_data["d"]), "big")
        p = int.from_bytes(_base64url_decode(key_data["p"]), "big")
        q = int.from_bytes(_base64url_decode(key_data["q"]), "big")
        dp = int.from_bytes(_base64url_decode(key_data["dp"]), "big")
        dq = int.from_bytes(_base64url_decode(key_data["dq"]), "big")
        qi = int.from_bytes(_base64url_decode(key_data["qi"]), "big")

        from cryptography.hazmat.primitives.asymmetric.rsa import (
            RSAPrivateNumbers,
            RSAPublicNumbers,
        )

        pub_numbers = RSAPublicNumbers(e, n)
        priv_numbers = RSAPrivateNumbers(p, q, d, dp, dq, qi, pub_numbers)
        private_key = priv_numbers.private_key()
        public_key = private_key.public_key()

        return private_key, public_key, kid

    def _generate_keypair(self) -> tuple[RSAPrivateKey, RSAPublicKey, str]:
        """Generate a new RSA-2048 keypair for development."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        return private_key, public_key, "dev-key-1"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(s: str) -> bytes:
    padding_needed = 4 - len(s) % 4
    if padding_needed != 4:
        s += "=" * padding_needed
    return base64.urlsafe_b64decode(s)
