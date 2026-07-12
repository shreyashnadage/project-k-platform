"""Trust Graph FastAPI application — internal API for trust scoring."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from fastapi import FastAPI
from pydantic import BaseModel

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware

from .models import TrustScore
from .service import TrustGraphService

configure_logging(json_output=True)

app = FastAPI(title="Trust Graph - Proprietary Scoring", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)

graph_service = TrustGraphService()


class RecordAttestationRequest(BaseModel):
    vendor_id: UUID
    anchor_id: UUID


class RecordRepaymentRequest(BaseModel):
    vendor_id: UUID
    anchor_id: UUID
    amount: str
    on_time: bool


class TrustScoreRequest(BaseModel):
    vendor_id: UUID
    anchor_id: UUID


@app.post("/graph/attestation")
def record_attestation(request: RecordAttestationRequest) -> dict[str, str]:
    graph_service.record_attestation(request.vendor_id, request.anchor_id)
    return {"status": "recorded"}


@app.post("/graph/repayment")
def record_repayment(request: RecordRepaymentRequest) -> dict[str, str]:
    from decimal import Decimal

    graph_service.record_repayment(
        request.vendor_id, request.anchor_id, Decimal(request.amount), request.on_time
    )
    return {"status": "recorded"}


@app.post("/graph/trust-score", response_model=TrustScore)
def compute_trust_score(request: TrustScoreRequest) -> TrustScore:
    return graph_service.compute_trust_score(request.vendor_id, request.anchor_id)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "trust-graph"}
