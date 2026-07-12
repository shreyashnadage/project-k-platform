"""Ory Kratos + Hydra adapter for borrower/vendor CIAM.

Implements both TokenVerifier (via Hydra's JWKS) and IdentityProvider
(via Kratos admin API). All URLs config-driven from identity.yaml.

This adapter is NOT used in Phase 1 — it's the Phase 3 implementation.
Included now so the protocol/factory layer is complete from day one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import jwt as pyjwt
import structlog

from libs.auth.types import (
    AuthCredentials,
    IdentityRecord,
    OrgType,
    TokenClaims,
    TokenPair,
)

logger = structlog.get_logger()


class AuthenticationError(Exception):
    pass


class IdentityNotFoundError(Exception):
    pass


@dataclass
class KratosConfig:
    kratos_public_url: str = ""
    kratos_admin_url: str = ""
    hydra_public_url: str = ""
    hydra_admin_url: str = ""
    hydra_jwks_url: str = ""
    algorithms: list[str] = field(default_factory=lambda: ["RS256"])
    default_org_type: str = "vendor"


class KratosTokenVerifier:
    """Verifies Hydra-issued access tokens via JWKS."""

    def __init__(self, config: KratosConfig) -> None:
        self._config = config
        self._jwks_client: pyjwt.PyJWKClient | None = None

    async def verify(self, token: str) -> TokenClaims:
        if not self._config.hydra_jwks_url:
            raise AuthenticationError("Hydra JWKS URL not configured")
        try:
            jwks = self._get_jwks_client()
            signing_key = jwks.get_signing_key_from_jwt(token)
            decoded = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=self._config.algorithms,
                options={"verify_aud": False},
            )
        except pyjwt.ExpiredSignatureError as e:
            raise AuthenticationError("Token expired") from e
        except pyjwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}") from e

        return TokenClaims(
            subject=decoded.get("sub", ""),
            issuer=decoded.get("iss", ""),
            org_id=decoded.get("org_id"),
            org_type=OrgType(decoded.get("org_type", self._config.default_org_type)),
            phone=decoded.get("phone"),
            raw=decoded,
        )

    async def get_jwks_uri(self) -> str:
        return self._config.hydra_jwks_url

    def _get_jwks_client(self) -> pyjwt.PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = pyjwt.PyJWKClient(self._config.hydra_jwks_url)
        return self._jwks_client


class KratosIdentityProvider:
    """Manages borrower/vendor identities via Kratos admin API."""

    def __init__(self, config: KratosConfig) -> None:
        self._config = config

    async def create_identity(self, traits: dict) -> IdentityRecord:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._config.kratos_admin_url}/admin/identities",
                json={
                    "schema_id": "borrower",
                    "traits": traits,
                },
            )
            if resp.status_code != 201:
                logger.error("kratos_create_failed", status=resp.status_code, body=resp.text)
                raise AuthenticationError(f"Identity creation failed: {resp.status_code}")
            data = resp.json()
            return IdentityRecord(
                identity_id=data["id"],
                org_type=OrgType(traits.get("org_type", self._config.default_org_type)),
                traits=data.get("traits", {}),
                state=data.get("state", "active"),
                verified=False,
            )

    async def authenticate(self, credentials: AuthCredentials) -> TokenPair:
        raise NotImplementedError("OTP authentication flow handled by Kratos self-service UI")

    async def get_identity(self, identity_id: str) -> IdentityRecord:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config.kratos_admin_url}/admin/identities/{identity_id}",
            )
            if resp.status_code == 404:
                raise IdentityNotFoundError(f"Identity {identity_id} not found")
            if resp.status_code != 200:
                raise AuthenticationError(f"Identity lookup failed: {resp.status_code}")
            data = resp.json()
            traits = data.get("traits", {})
            return IdentityRecord(
                identity_id=data["id"],
                org_type=OrgType(traits.get("org_type", self._config.default_org_type)),
                traits=traits,
                state=data.get("state", "active"),
                verified=bool(data.get("verifiable_addresses")),
            )

    async def update_traits(self, identity_id: str, traits: dict) -> IdentityRecord:
        current = await self.get_identity(identity_id)
        merged_traits = {**current.traits, **traits}
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self._config.kratos_admin_url}/admin/identities/{identity_id}",
                json={
                    "schema_id": "borrower",
                    "traits": merged_traits,
                    "state": current.state,
                },
            )
            if resp.status_code != 200:
                raise AuthenticationError(f"Trait update failed: {resp.status_code}")
            data = resp.json()
            return IdentityRecord(
                identity_id=data["id"],
                org_type=OrgType(merged_traits.get("org_type", self._config.default_org_type)),
                traits=data.get("traits", {}),
                state=data.get("state", "active"),
                verified=current.verified,
            )

    async def revoke_session(self, session_id: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self._config.kratos_admin_url}/admin/sessions/{session_id}",
            )
            if resp.status_code not in (200, 204, 404):
                logger.warning("session_revoke_failed", session_id=session_id, status=resp.status_code)
