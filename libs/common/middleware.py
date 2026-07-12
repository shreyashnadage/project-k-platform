"""ASGI middleware for correlation ID propagation and DPDP RBAC enforcement."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog
from dpdp_core.middleware.consent_context import set_processing_context
from dpdp_core.middleware.rbac import check_role_access, extract_roles_from_token
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
    """Enforces DPDP-configured RBAC using Keycloak JWT roles.

    Enabled only when DPDP_RBAC_ENABLED=true. In dev mode (default),
    the middleware passes through all requests and sets a default
    processing context.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        set_processing_context(purpose="request_processing")

        if not RBAC_ENABLED:
            return await call_next(request)

        path = request.url.path
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            # Protected paths require auth when RBAC is on
            if _is_protected_path(path):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authorization header required"},
                )
            return await call_next(request)

        try:
            token = auth_header.removeprefix("Bearer ")
            decoded = _decode_token(token)
            roles = extract_roles_from_token(decoded)

            if not check_role_access(path, roles):
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
        except Exception:
            logger.debug("rbac_token_decode_skipped", path=path)

        return await call_next(request)


class _AuthError(Exception):
    pass


_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and KEYCLOAK_JWKS_URL:
        import jwt

        _jwks_client = jwt.PyJWKClient(KEYCLOAK_JWKS_URL)
    return _jwks_client


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    When KEYCLOAK_JWKS_URL is configured, validates signature against Keycloak.
    Otherwise falls back to unverified decode (dev mode only).
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


def _is_protected_path(path: str) -> bool:
    """Check if a path requires authentication based on RBAC config."""
    protected_prefixes = ("/ops/", "/dpdp/")
    return any(path.startswith(p) for p in protected_prefixes)
