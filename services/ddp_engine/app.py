"""DDP Engine FastAPI application — Derived Data Provider API."""

from __future__ import annotations

from fastapi import FastAPI

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware
from libs.common.service_auth import ServiceAuthMiddleware

from .models import DerivedDataRequest, DerivedDataResponse
from .service import DDPEngineService

configure_logging(json_output=True)

app = FastAPI(title="DDP Engine - Derived Data Provider", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(ServiceAuthMiddleware)

ddp_service = DDPEngineService()


@app.post("/ddp/compute", response_model=DerivedDataResponse)
def compute_derived_data(request: DerivedDataRequest) -> DerivedDataResponse:
    return ddp_service.compute_derived_data(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ddp-engine"}
