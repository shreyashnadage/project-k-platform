"""VDP Wedge FastAPI application — invoice ingestion API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware
from libs.zen_rules.engine import ZenDecisionEngine

from .models import (
    InvoiceIngestionRequest,
    InvoiceIngestionResponse,
    Kind1CheckRequest,
    Kind1CheckResponse,
)
from .service import VDPWedgeService

configure_logging(json_output=True)

app = FastAPI(title="VDP Wedge - Invoice Ingestion", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)

zen_engine = ZenDecisionEngine("rules/")
service = VDPWedgeService(zen_engine)


@app.post("/invoices/ingest", response_model=InvoiceIngestionResponse)
def ingest_invoice(request: InvoiceIngestionRequest) -> InvoiceIngestionResponse:
    return service.ingest_invoice(request)


@app.post("/invoices/kind1-check", response_model=Kind1CheckResponse)
def check_kind1(request: Kind1CheckRequest) -> Kind1CheckResponse:
    try:
        return service.check_kind1(request.invoice_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vdp-wedge"}
