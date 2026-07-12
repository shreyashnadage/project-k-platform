"""Simple in-memory sliding window rate limiter.

For production, replace with Redis-backed implementation.
Toggle via RATE_LIMIT_ENABLED=true, configure with RATE_LIMIT_RPM.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_RPM = int(os.environ.get("RATE_LIMIT_RPM", "60"))
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter per client IP."""

    def __init__(self, app, rpm: int = RATE_LIMIT_RPM) -> None:
        super().__init__(app)
        self.rpm = rpm
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - WINDOW_SECONDS

        timestamps = self._requests[client_ip]
        self._requests[client_ip] = [t for t in timestamps if t > window_start]

        if len(self._requests[client_ip]) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.rpm} requests per minute.",
            )

        self._requests[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(
            self.rpm - len(self._requests[client_ip])
        )
        return response
