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
            return await call_next(request)

        try:
            import jwt

            token = auth_header.removeprefix("Bearer ")
            decoded = jwt.decode(token, options={"verify_signature": False})
            roles = extract_roles_from_token(decoded)

            if not check_role_access(path, roles):
                logger.warning("rbac_denied", path=path, roles=list(roles))
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Insufficient role for this endpoint"},
                )

        except Exception:
            logger.debug("rbac_token_decode_skipped", path=path)

        return await call_next(request)
