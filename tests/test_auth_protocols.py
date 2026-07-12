"""Tests for the auth protocol abstraction layer (libs/auth/).

Verifies:
- TokenVerifier and IdentityProvider protocols are implementable
- Keycloak adapter handles JWKS failures correctly
- Factory selects providers based on identity.yaml config
- Tenancy config loads and provides correct values
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.auth.adapters.keycloak import (
    AuthenticationError,
    KeycloakConfig,
    KeycloakTokenVerifier,
)
from libs.auth.factory import (
    _resolve_env_vars,
    get_borrower_verifier,
    get_workforce_verifier,
    reset_config_cache,
)
from libs.auth.types import AuthCredentials, OrgType, TokenClaims, TokenPair
from libs.db.rls import (
    get_bypass_roles,
    get_session_variable,
    get_tenant_claim_path,
    reset_tenancy_cache,
    should_bypass_rls,
)


# ─── Protocol Conformance ──────────────────────────────────


class TestTokenVerifierProtocol:
    """Verify that our adapters satisfy the TokenVerifier protocol structurally."""

    def test_keycloak_adapter_has_verify_method(self):
        config = KeycloakConfig(jwks_url="http://localhost:8080/certs")
        verifier = KeycloakTokenVerifier(config)
        assert hasattr(verifier, "verify")
        assert hasattr(verifier, "get_jwks_uri")

    def test_kratos_adapter_has_verify_method(self):
        from libs.auth.adapters.kratos import KratosConfig, KratosTokenVerifier

        config = KratosConfig(hydra_jwks_url="http://localhost:4444/.well-known/jwks.json")
        verifier = KratosTokenVerifier(config)
        assert hasattr(verifier, "verify")
        assert hasattr(verifier, "get_jwks_uri")


class TestIdentityProviderProtocol:
    """Verify that Kratos adapter satisfies the IdentityProvider protocol."""

    def test_kratos_adapter_has_required_methods(self):
        from libs.auth.adapters.kratos import KratosConfig, KratosIdentityProvider

        config = KratosConfig(kratos_admin_url="http://localhost:4434")
        provider = KratosIdentityProvider(config)
        assert hasattr(provider, "create_identity")
        assert hasattr(provider, "authenticate")
        assert hasattr(provider, "get_identity")
        assert hasattr(provider, "update_traits")
        assert hasattr(provider, "revoke_session")


# ─── Keycloak Adapter ──────────────────────────────────────


class TestKeycloakTokenVerifier:
    @pytest.fixture()
    def config(self):
        return KeycloakConfig(
            jwks_url="http://keycloak:8080/realms/ocen-platform/protocol/openid-connect/certs",
            issuer="http://keycloak:8080/realms/ocen-platform",
            audience="la-orchestrator",
            role_claim_path="realm_access.roles",
        )

    @pytest.fixture()
    def verifier(self, config):
        return KeycloakTokenVerifier(config)

    async def test_get_jwks_uri_returns_config_url(self, verifier, config):
        uri = await verifier.get_jwks_uri()
        assert uri == config.jwks_url

    async def test_verify_raises_on_invalid_token(self, verifier):
        import jwt as pyjwt

        with patch.object(verifier, "_get_jwks_client") as mock_jwks:
            mock_jwks.return_value.get_signing_key_from_jwt.side_effect = pyjwt.InvalidTokenError("bad")
            with pytest.raises(AuthenticationError, match="Invalid token"):
                await verifier.verify("invalid.token.here")

    def test_extract_roles_from_nested_claim(self, verifier):
        decoded = {"realm_access": {"roles": ["platform-admin", "operations"]}}
        roles = verifier._extract_roles(decoded)
        assert roles == {"platform-admin", "operations"}

    def test_extract_roles_missing_path_returns_empty(self, verifier):
        decoded = {"other_claim": "value"}
        roles = verifier._extract_roles(decoded)
        assert roles == set()


# ─── Factory ───────────────────────────────────────────────


class TestAuthFactory:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        reset_config_cache()
        yield
        reset_config_cache()

    def test_resolve_env_vars(self):
        os.environ["TEST_AUTH_URL"] = "http://test.example.com"
        try:
            result = _resolve_env_vars("${TEST_AUTH_URL}/certs")
            assert result == "http://test.example.com/certs"
        finally:
            del os.environ["TEST_AUTH_URL"]

    def test_resolve_env_vars_missing_returns_empty(self):
        result = _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == ""

    def test_resolve_env_vars_no_placeholder_passthrough(self):
        result = _resolve_env_vars("plain-string")
        assert result == "plain-string"

    def test_get_workforce_verifier_returns_keycloak(self, tmp_path):
        config_file = tmp_path / "identity.yaml"
        config_file.write_text(
            "workforce:\n"
            "  provider: keycloak\n"
            "  jwks_url: http://localhost:8080/certs\n"
        )
        os.environ["IDENTITY_CONFIG_PATH"] = str(config_file)
        try:
            verifier = get_workforce_verifier()
            assert isinstance(verifier, KeycloakTokenVerifier)
        finally:
            del os.environ["IDENTITY_CONFIG_PATH"]

    def test_get_workforce_verifier_unknown_provider_raises(self, tmp_path, monkeypatch):
        config_file = tmp_path / "identity.yaml"
        config_file.write_text("workforce:\n  provider: unknown\n")
        monkeypatch.setenv("IDENTITY_CONFIG_PATH", str(config_file))
        reset_config_cache()
        with pytest.raises(RuntimeError, match="Unknown workforce auth provider"):
            get_workforce_verifier()

    def test_get_borrower_verifier_returns_kratos(self, tmp_path):
        config_file = tmp_path / "identity.yaml"
        config_file.write_text(
            "borrower:\n"
            "  provider: kratos\n"
            "  hydra_jwks_url: http://localhost:4444/.well-known/jwks.json\n"
        )
        os.environ["IDENTITY_CONFIG_PATH"] = str(config_file)
        try:
            from libs.auth.adapters.kratos import KratosTokenVerifier

            verifier = get_borrower_verifier()
            assert isinstance(verifier, KratosTokenVerifier)
        finally:
            del os.environ["IDENTITY_CONFIG_PATH"]


# ─── Types ─────────────────────────────────────────────────


class TestAuthTypes:
    def test_token_claims_construction(self):
        claims = TokenClaims(
            subject="user-123",
            roles={"platform-admin", "operations"},
            org_id="GSTIN123",
            org_type=OrgType.vendor,
        )
        assert claims.subject == "user-123"
        assert "platform-admin" in claims.roles
        assert claims.org_type == OrgType.vendor

    def test_auth_credentials_defaults(self):
        creds = AuthCredentials(identifier="+919876543210")
        assert creds.credential_type == "otp"
        assert creds.credential_value == ""

    def test_token_pair_construction(self):
        pair = TokenPair(
            access_token="abc",
            refresh_token="def",
            expires_in=3600,
        )
        assert pair.token_type == "Bearer"
        assert pair.expires_in == 3600


# ─── Tenancy Config ────────────────────────────────────────


class TestTenancyConfig:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        reset_tenancy_cache()
        yield
        reset_tenancy_cache()

    def test_load_tenancy_config_defaults(self, tmp_path):
        config_file = tmp_path / "tenancy.yaml"
        config_file.write_text(
            "tenant_claim_path: org_id\n"
            "session_variable: app.tenant_id\n"
            "bypass_roles:\n"
            "  - platform-admin\n"
            "  - operations\n"
        )
        os.environ["TENANCY_CONFIG_PATH"] = str(config_file)
        try:
            assert get_tenant_claim_path() == "org_id"
            assert get_session_variable() == "app.tenant_id"
            assert get_bypass_roles() == {"platform-admin", "operations"}
        finally:
            del os.environ["TENANCY_CONFIG_PATH"]

    def test_should_bypass_rls_admin(self, tmp_path):
        config_file = tmp_path / "tenancy.yaml"
        config_file.write_text("bypass_roles:\n  - platform-admin\n")
        os.environ["TENANCY_CONFIG_PATH"] = str(config_file)
        try:
            assert should_bypass_rls({"platform-admin"}) is True
            assert should_bypass_rls({"anchor-manager"}) is False
        finally:
            del os.environ["TENANCY_CONFIG_PATH"]
