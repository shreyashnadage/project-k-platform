"""ASGI middleware for correlation ID propagation and platform RBAC enforcement.

RBAC posture (when DPDP_RBAC_ENABLED=true) is fail-closed:
  1. A request to a path listed in authz.yaml's public_paths is always allowed.
  2. Every other request must present a valid Bearer token.
  3. The token's roles must match an entry in dpdp_config.yaml's `rbac:` section
     for that path — if no entry covers the path, access is DENIED (not
     allowed, unlike dpdp_core's own permissive default).
  4. Any failure to verify the token (expired, invalid, unreachable JWKS)
     results in a 401 — never a silent pass-through.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml
from dpdp_core.middleware.consent_context import set_processing_context
from dpdp_core.middleware.rbac import extract_roles_from_token
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from libs.common.logging import correlation_id_var, new_correlation_id

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger()

CORRELATION_ID_HEADER = "X-Correlation-ID"
RBAC_ENABLED = os.environ.get("DPDP_RBAC_ENABLED", "false").lower() == "true"
KEYCLOAK_JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL", "")
KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER", "")
KEYCLOAK_AUDIENCE = os.environ.get("KEYCLOAK_AUDIENCE", "")
INTEGRATION_MODE = os.environ.get("INTEGRATION_MODE", "")
AUTHZ_CONFIG_PATH = os.environ.get("AUTHZ_CONFIG_PATH", "authz.yaml")
DPDP_CONFIG_PATH = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")


def _has_always_protected_paths() -> bool:
    path = Path(AUTHZ_CONFIG_PATH)
    if not path.exists():
        return False
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return bool(raw.get("always_protected_paths"))


if (RBAC_ENABLED or _has_always_protected_paths()) and not KEYCLOAK_JWKS_URL and INTEGRATION_MODE != "sandbox":
    raise RuntimeError(
        "JWT signature verification is required (DPDP_RBAC_ENABLED=true, and/or "
        "authz.yaml declares always_protected_paths such as /dpdp/rights) but "
        "KEYCLOAK_JWKS_URL is not set. Refusing to start with unverified JWT "
        "decoding outside INTEGRATION_MODE=sandbox. Set KEYCLOAK_JWKS_URL "
        "(e.g. http://keycloak:8080/realms/ocen-platform/protocol/openid-connect/certs) "
        "or set INTEGRATION_MODE=sandbox for local development."
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get(CORRELATION_ID_HEADER)
        if incoming_id:
            correlation_id_var.set(incoming_id)
            cid = incoming_id
        else:
            cid = new_correlation_id()

        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = cid
        return response


class DPDPRBACMiddleware(BaseHTTPMiddleware):
    """Enforces fail-closed RBAC using Keycloak JWT roles.

    Disabled (full pass-through) only when DPDP_RBAC_ENABLED=false, which is
    the local-dev default. Once enabled, every request must either match an
    explicit public path (authz.yaml) or present a Bearer token whose roles
    are allowed for that path per dpdp_config.yaml's rbac section.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        set_processing_context(purpose="request_processing")

        path = request.url.path
        always_protected = _is_always_protected_path(path)

        if not RBAC_ENABLED and not always_protected:
            return await call_next(request)

        if _is_public_path(path):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authorization header required"},
            )

        try:
            token = auth_header.removeprefix("Bearer ")
            decoded = _decode_token(token)
            roles = extract_roles_from_token(decoded)

            if not _check_role_access_default_deny(path, roles):
                logger.warning("rbac_denied", path=path, roles=list(roles))
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Insufficient role for this endpoint"},
                )

        except _AuthError as e:
            logger.warning("rbac_auth_failed", path=path, error=str(e))
            return JSONResponse(
                status_code=401,
                content={"detail": str(e)},
            )
        except Exception as e:
            # Fail closed: any unexpected decode/JWKS failure is a 401, never
            # a silent pass-through.
            logger.error("rbac_verification_error", path=path, error=str(e))
            return JSONResponse(
                status_code=401,
                content={"detail": "Unable to verify authorization"},
            )

        return await call_next(request)


class _AuthError(Exception):
    pass


_jwks_client = None
_public_paths_cache: list[str] | None = None
_always_protected_paths_cache: list[str] | None = None
_rbac_map_cache: dict[str, set[str]] | None = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and KEYCLOAK_JWKS_URL:
        import jwt

        _jwks_client = jwt.PyJWKClient(KEYCLOAK_JWKS_URL)
    return _jwks_client


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    When KEYCLOAK_JWKS_URL is configured, validates signature against Keycloak.
    Otherwise falls back to unverified decode — only reachable when
    INTEGRATION_MODE=sandbox, enforced by the module-level startup check above.
    """
    import jwt

    jwks = _get_jwks_client()
    if jwks:
        try:
            signing_key = jwks.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=KEYCLOAK_ISSUER or None,
                audience=KEYCLOAK_AUDIENCE or None,
                options={
                    "verify_iss": bool(KEYCLOAK_ISSUER),
                    "verify_aud": bool(KEYCLOAK_AUDIENCE),
                },
            )
        except jwt.ExpiredSignatureError as e:
            raise _AuthError("Token expired") from e
        except jwt.InvalidTokenError as e:
            raise _AuthError("Invalid token") from e
    else:
        return jwt.decode(token, options={"verify_signature": False})


def _load_public_paths() -> list[str]:
    global _public_paths_cache
    if _public_paths_cache is None:
        path = Path(AUTHZ_CONFIG_PATH)
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            _public_paths_cache = [entry["path"] for entry in raw.get("public_paths", [])]
        else:
            _public_paths_cache = []
    return _public_paths_cache


def _load_always_protected_paths() -> list[str]:
    global _always_protected_paths_cache
    if _always_protected_paths_cache is None:
        path = Path(AUTHZ_CONFIG_PATH)
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            _always_protected_paths_cache = [
                entry["path"] for entry in raw.get("always_protected_paths", [])
            ]
        else:
            _always_protected_paths_cache = []
    return _always_protected_paths_cache


def _is_always_protected_path(path: str) -> bool:
    return any(path.startswith(p) for p in _load_always_protected_paths())


def _load_rbac_map() -> dict[str, set[str]]:
    global _rbac_map_cache
    if _rbac_map_cache is None:
        path = Path(DPDP_CONFIG_PATH)
        rbac_map: dict[str, set[str]] = {}
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            for entry in raw.get("rbac", []):
                rbac_map[entry["path_prefix"]] = set(entry["allowed_roles"])
        _rbac_map_cache = rbac_map
    return _rbac_map_cache


def reset_authz_cache() -> None:
    """Clear cached authz.yaml/dpdp_config.yaml reads — for tests."""
    global _public_paths_cache, _always_protected_paths_cache, _rbac_map_cache
    _public_paths_cache = None
    _always_protected_paths_cache = None
    _rbac_map_cache = None


def _is_public_path(path: str) -> bool:
    return any(path.startswith(p) for p in _load_public_paths())


def _check_role_access_default_deny(path: str, roles: set[str]) -> bool:
    """Fail-closed role check: a path with no matching rbac_map entry is DENIED.

    This intentionally does not delegate to dpdp_core.check_role_access,
    which allows any path not present in its role map — the opposite,
    permissive default this platform's RBAC posture requires.
    """
    rbac_map = _load_rbac_map()
    for prefix, allowed_roles in rbac_map.items():
        if path.startswith(prefix):
            return bool(roles & allowed_roles)
    return False
