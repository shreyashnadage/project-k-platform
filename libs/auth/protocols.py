"""Protocol definitions for identity and token verification.

Application code depends ONLY on these protocols. Concrete implementations
(Keycloak, Kratos, Auth0, Zitadel) are selected via identity.yaml config
and instantiated by libs/auth/factory.py.

This mirrors the pattern in libs/integrations/protocols.py (UdyamClient, etc.).
"""

from __future__ import annotations

from typing import Protocol

from libs.auth.types import AuthCredentials, IdentityRecord, TokenClaims, TokenPair


class TokenVerifier(Protocol):
    """Verifies and decodes bearer tokens from any OIDC-compliant provider.

    Implementations handle JWKS fetching, caching, rotation, and claim
    extraction. Application code never interacts with provider-specific
    token formats.
    """

    async def verify(self, token: str) -> TokenClaims:
        """Verify token signature and return decoded claims.

        Raises AuthenticationError on invalid/expired/revoked tokens.
        """
        ...

    async def get_jwks_uri(self) -> str:
        """Return the JWKS endpoint URI for this provider."""
        ...


class IdentityProvider(Protocol):
    """Manages identity lifecycle — registration, authentication, lookup.

    Used for borrower/vendor CIAM (Kratos) and potentially anchor CIAM.
    Workforce IAM (Keycloak) typically only needs TokenVerifier since
    identity management happens in the Keycloak admin console.
    """

    async def create_identity(self, traits: dict) -> IdentityRecord:
        """Create a new identity with the given traits."""
        ...

    async def authenticate(self, credentials: AuthCredentials) -> TokenPair:
        """Authenticate with credentials and return tokens."""
        ...

    async def get_identity(self, identity_id: str) -> IdentityRecord:
        """Retrieve an identity by its provider-assigned ID."""
        ...

    async def update_traits(self, identity_id: str, traits: dict) -> IdentityRecord:
        """Update identity traits (e.g., after Udyam verification)."""
        ...

    async def revoke_session(self, session_id: str) -> None:
        """Revoke an active session."""
        ...


class SMSGateway(Protocol):
    """Sends OTP and transactional SMS — provider-agnostic.

    Implementations: MSG91, Kaleyra, sandbox mock.
    """

    async def send_otp(self, phone: str, otp: str, template_id: str = "") -> bool:
        """Send OTP to phone number. Returns True if delivery accepted."""
        ...

    async def verify_otp(self, phone: str, otp: str) -> bool:
        """Verify OTP entered by user. Returns True if valid."""
        ...
