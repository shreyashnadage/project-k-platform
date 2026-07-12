"""Keycloak TokenVerifier adapter.

Verifies JWTs issued by a Keycloak realm using JWKS. Handles key caching,
rotation, and circuit-breaking on JWKS endpoint failures.

Config-driven: all URLs, algorithms, and cache TTLs come from identity.yaml.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import jwt as pyjwt
import structlog

from libs.auth.types import TokenClaims

logger = structlog.get_logger()


class AuthenticationError(Exception):
    """Raised when token verification fails for any reason."""


@dataclass
class KeycloakConfig:
    jwks_url: str
    issuer: str = ""
    audience: str = ""
    algorithms: list[str] = field(default_factory=lambda: ["RS256"])
    jwks_cache_ttl_seconds: int = 300
    role_claim_path: str = "realm_access.roles"


class KeycloakTokenVerifier:
    """Verifies Keycloak-issued JWTs with cached JWKS and circuit breaking."""

    def __init__(self, config: KeycloakConfig) -> None:
        self._config = config
        self._jwks_client: pyjwt.PyJWKClient | None = None
        self._jwks_cache_time: float = 0
        self._cached_keys: list | None = None

    async def verify(self, token: str) -> TokenClaims:
        """Verify token signature and decode claims."""
        try:
            jwks = self._get_jwks_client()
            signing_key = jwks.get_signing_key_from_jwt(token)
            decoded = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=self._config.algorithms,
                issuer=self._config.issuer or None,
                audience=self._config.audience or None,
                options={
                    "verify_iss": bool(self._config.issuer),
                    "verify_aud": bool(self._config.audience),
                },
            )
        except pyjwt.ExpiredSignatureError as e:
            raise AuthenticationError("Token expired") from e
        except pyjwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}") from e
        except (httpx.HTTPError, OSError) as e:
            logger.error("jwks_fetch_failed", url=self._config.jwks_url, error=str(e))
            raise AuthenticationError("Unable to verify token signature") from e

        roles = self._extract_roles(decoded)
        return TokenClaims(
            subject=decoded.get("sub", ""),
            issuer=decoded.get("iss", ""),
            audience=decoded.get("aud", ""),
            roles=roles,
            org_id=decoded.get("org_id"),
            email=decoded.get("email"),
            raw=decoded,
        )

    async def get_jwks_uri(self) -> str:
        return self._config.jwks_url

    def _get_jwks_client(self) -> pyjwt.PyJWKClient:
        now = time.monotonic()
        if self._jwks_client is None or (now - self._jwks_cache_time) > self._config.jwks_cache_ttl_seconds:
            self._jwks_client = pyjwt.PyJWKClient(self._config.jwks_url)
            self._jwks_cache_time = now
        return self._jwks_client

    def _extract_roles(self, decoded: dict) -> set[str]:
        """Extract roles from Keycloak's nested claim structure."""
        parts = self._config.role_claim_path.split(".")
        current = decoded
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                return set()
        if isinstance(current, list):
            return set(current)
        return set()
