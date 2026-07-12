"""Config-driven factory for auth providers.

Reads identity.yaml to determine which TokenVerifier and IdentityProvider
implementations to instantiate. Application code calls these factory
functions — never imports adapters directly.

Pattern mirrors libs/integrations/factory.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from libs.auth.adapters.keycloak import KeycloakConfig, KeycloakTokenVerifier
from libs.auth.protocols import IdentityProvider, TokenVerifier

_identity_config_cache: dict[str, Any] | None = None


def _load_identity_config() -> dict[str, Any]:
    global _identity_config_cache
    if _identity_config_cache is not None:
        return _identity_config_cache
    config_path = os.environ.get("IDENTITY_CONFIG_PATH", "identity.yaml")
    path = Path(config_path)
    if not path.exists():
        _identity_config_cache = {}
        return _identity_config_cache
    with open(path) as f:
        _identity_config_cache = yaml.safe_load(f) or {}
    return _identity_config_cache


def _resolve_env_vars(value: str) -> str:
    """Resolve ${ENV_VAR} placeholders in config values."""
    if not isinstance(value, str) or "${" not in value:
        return value
    import re
    def replacer(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")
    return re.sub(r"\$\{(\w+)}", replacer, value)


def get_workforce_verifier() -> TokenVerifier:
    """Get the workforce (ops/admin/lender) token verifier.

    Currently always Keycloak. Switchable via identity.yaml → workforce.provider.
    """
    config = _load_identity_config()
    workforce = config.get("workforce", {})
    provider = workforce.get("provider", "keycloak")

    if provider == "keycloak":
        jwks_url = _resolve_env_vars(workforce.get("jwks_url", os.environ.get("KEYCLOAK_JWKS_URL", "")))
        return KeycloakTokenVerifier(
            KeycloakConfig(
                jwks_url=jwks_url,
                issuer=_resolve_env_vars(workforce.get("issuer", os.environ.get("KEYCLOAK_ISSUER", ""))),
                audience=_resolve_env_vars(workforce.get("audience", os.environ.get("KEYCLOAK_AUDIENCE", ""))),
                algorithms=workforce.get("algorithms", ["RS256"]),
                jwks_cache_ttl_seconds=workforce.get("jwks_cache_ttl_seconds", 300),
                role_claim_path=workforce.get("role_claim_path", "realm_access.roles"),
            )
        )

    msg = f"Unknown workforce auth provider: {provider!r}. Supported: 'keycloak'."
    raise RuntimeError(msg)


def get_borrower_verifier() -> TokenVerifier:
    """Get the borrower/vendor (CIAM) token verifier.

    Currently Ory Hydra (paired with Kratos). Switchable via identity.yaml → borrower.provider.
    """
    config = _load_identity_config()
    borrower = config.get("borrower", {})
    provider = borrower.get("provider", "kratos")

    if provider == "kratos":
        from libs.auth.adapters.kratos import KratosConfig, KratosTokenVerifier
        return KratosTokenVerifier(
            KratosConfig(
                hydra_jwks_url=_resolve_env_vars(borrower.get("hydra_jwks_url", "")),
                hydra_public_url=_resolve_env_vars(borrower.get("hydra_public_url", "")),
                algorithms=borrower.get("algorithms", ["RS256"]),
                default_org_type=borrower.get("default_org_type", "vendor"),
            )
        )

    msg = f"Unknown borrower auth provider: {provider!r}. Supported: 'kratos'."
    raise RuntimeError(msg)


def get_borrower_identity_provider() -> IdentityProvider:
    """Get the borrower/vendor identity provider (registration, lookup, trait updates)."""
    config = _load_identity_config()
    borrower = config.get("borrower", {})
    provider = borrower.get("provider", "kratos")

    if provider == "kratos":
        from libs.auth.adapters.kratos import KratosConfig, KratosIdentityProvider
        return KratosIdentityProvider(
            KratosConfig(
                kratos_public_url=_resolve_env_vars(borrower.get("kratos_public_url", "")),
                kratos_admin_url=_resolve_env_vars(borrower.get("kratos_admin_url", "")),
                hydra_public_url=_resolve_env_vars(borrower.get("hydra_public_url", "")),
                hydra_admin_url=_resolve_env_vars(borrower.get("hydra_admin_url", "")),
                default_org_type=borrower.get("default_org_type", "vendor"),
            )
        )

    msg = f"Unknown borrower identity provider: {provider!r}. Supported: 'kratos'."
    raise RuntimeError(msg)


def reset_config_cache() -> None:
    """Clear cached config — for tests."""
    global _identity_config_cache
    _identity_config_cache = None
