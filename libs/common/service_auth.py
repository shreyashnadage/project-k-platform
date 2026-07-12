"""Service-to-service bearer-token verification for internal APIs.

Applies to services that are only ever called by other platform services
(ddp_engine, vdp_wedge, trust_graph) — not by end users. Unlike
DPDPRBACMiddleware, this checks only that the caller presents a valid,
signed token from a known Keycloak client (e.g. the existing la-orchestrator
or ddp-engine service-account clients); it does not do per-role
authorization — there's only one trust tier here: "verified internal
caller".

Disabled (full pass-through except a fail-fast startup guard) unless
SERVICE_AUTH_ENABLED=true, matching the platform's dev-convenience default
posture elsewhere.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger()

SERVICE_AUTH_ENABLED = os.environ.get("SERVICE_AUTH_ENABLED", "false").lower() == "true"
KEYCLOAK_JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL", "")
KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER", "")
INTEGRATION_MODE = os.environ.get("INTEGRATION_MODE", "")
PUBLIC_PATHS = ("/health",)

if SERVICE_AUTH_ENABLED and not KEYCLOAK_JWKS_URL and INTEGRATION_MODE != "sandbox":
    raise RuntimeError(
        "SERVICE_AUTH_ENABLED=true requires KEYCLOAK_JWKS_URL to be set so "
        "caller tokens can be verified. Refusing to start with unverified "
        "tokens outside INTEGRATION_MODE=sandbox."
    )


class _ServiceAuthError(Exception):
    pass


_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and KEYCLOAK_JWKS_URL:
        import jwt

        _jwks_client = jwt.PyJWKClient(KEYCLOAK_JWKS_URL)
    return _jwks_client


def _verify_service_token(token: str) -> dict:
    import jwt

    jwks = _get_jwks_client()
    if not jwks:
        # Only reachable in INTEGRATION_MODE=sandbox — enforced by the
        # module-level startup guard above.
        return jwt.decode(token, options={"verify_signature": False})
    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER or None,
            options={"verify_iss": bool(KEYCLOAK_ISSUER), "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as e:
        raise _ServiceAuthError("Token expired") from e
    except jwt.InvalidTokenError as e:
        raise _ServiceAuthError("Invalid token") from e


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Requires a valid Keycloak service-client bearer token on every request
    except /health. Fails closed: any verification error is a 401, never a
    silent pass-through.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not SERVICE_AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authorization header required"},
            )

        try:
            token = auth_header.removeprefix("Bearer ")
            _verify_service_token(token)
        except _ServiceAuthError as e:
            logger.warning("service_auth_failed", path=path, error=str(e))
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except Exception as e:
            logger.error("service_auth_verification_error", path=path, error=str(e))
            return JSONResponse(
                status_code=401,
                content={"detail": "Unable to verify authorization"},
            )

        return await call_next(request)
