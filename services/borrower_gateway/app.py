"""Borrower Gateway FastAPI application — OCEN loan origination API."""

from __future__ import annotations

import os
from uuid import UUID  # noqa: TC003

import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from temporalio.client import Client as TemporalClient

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware
from libs.ocen_client.jws.signer import OcenJWSSigner
from libs.ocen_client.models.journey import (
    CreateLoanApplicationResponse,
    OcenAckResponse,
)
from libs.ocen_client.network_client import OcenNetworkClient

from .models import LoanApplicationRequest, LoanApplicationResponse, LoanApplicationStatus
from .service import get_gateway_service

configure_logging(json_output=True)
logger = structlog.get_logger()

app = FastAPI(title="Borrower Gateway - OCEN LA", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)

gateway_service = get_gateway_service()
ocen_client = OcenNetworkClient()
jws_signer = OcenJWSSigner()

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")

_temporal_client: TemporalClient | None = None


async def get_temporal_client() -> TemporalClient:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await TemporalClient.connect(
            TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE
        )
    return _temporal_client


# ─── Internal Borrower API ──────────────────────────────────────


@app.post("/loans/apply", response_model=LoanApplicationResponse)
async def apply_for_loan(request: LoanApplicationRequest) -> LoanApplicationResponse:
    response = gateway_service.initiate_application(request)

    try:
        temporal = await get_temporal_client()
        await temporal.start_workflow(
            "LoanOriginationWorkflow",
            {
                "loan_application_id": str(response.application_id),
                "vendor_gstin": request.vendor_gstin,
                "anchor_gstin": request.anchor_gstin,
                "invoice_id": str(request.invoice_id),
                "amount_requested": float(request.amount_requested),
            },
            id=response.workflow_id,
            task_queue=os.environ.get("TEMPORAL_TASK_QUEUE", "loan-origination"),
        )
        logger.info("workflow_started", workflow_id=response.workflow_id)
    except Exception as e:
        logger.error("workflow_start_failed", error=str(e), workflow_id=response.workflow_id)

    return response


class ApplicationStatusRequest(BaseModel):
    application_id: UUID


@app.post("/loans/status", response_model=LoanApplicationStatus)
def get_loan_status(request: ApplicationStatusRequest) -> LoanApplicationStatus:
    try:
        return gateway_service.get_status(request.application_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ─── OCEN Network Callback Endpoints ───────────────────────────


async def _verify_jws(request: Request) -> bool:
    """Verify inbound JWS signature from lender (if present)."""
    signature = request.headers.get("x-jws-signature")
    if not signature:
        return True  # No signature = dev mode, allow through
    body = await request.body()
    return jws_signer.verify(signature, body)


@app.post(
    "/v4.0.0alpha/loanApplications/createLoanResponse",
    response_model=OcenAckResponse,
)
async def create_loan_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN async callback — lender posts loan decision back to LA."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")

    ack = await ocen_client.handle_loan_response(response)

    # Signal the waiting Temporal workflow
    for loan_app in response.loan_applications:
        try:
            temporal = await get_temporal_client()
            workflow_id = f"loan-origination-{loan_app.loan_application_id}"
            handle = temporal.get_workflow_handle(workflow_id)
            await handle.signal(
                "lender_response_received",
                {
                    "offer": response.response.model_dump()
                    if response.response
                    else None,
                    "loan_application_id": loan_app.loan_application_id,
                },
            )
            logger.info(
                "lender_signal_sent",
                loan_application_id=loan_app.loan_application_id,
            )
        except Exception as e:
            logger.warning(
                "lender_signal_failed",
                loan_application_id=loan_app.loan_application_id,
                error=str(e),
            )

    return ack


@app.post(
    "/v4.0.0alpha/loanApplications/generateOffersResponse",
    response_model=OcenAckResponse,
)
async def generate_offers_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender posts generated offers back to LA."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/setOffersResponse",
    response_model=OcenAckResponse,
)
async def set_offers_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender confirms selected offer."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/loanAgreementResponse",
    response_model=OcenAckResponse,
)
async def loan_agreement_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender posts loan agreement for e-sign."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/grantLoanResponse",
    response_model=OcenAckResponse,
)
async def grant_loan_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender confirms loan grant."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/triggerDisbursementResponse",
    response_model=OcenAckResponse,
)
async def trigger_disbursement_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender confirms disbursement."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/triggerRepaymentResponse",
    response_model=OcenAckResponse,
)
async def trigger_repayment_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — repayment event from lender."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.post(
    "/v4.0.0alpha/loanApplications/setRepaymentPlanResponse",
    response_model=OcenAckResponse,
)
async def set_repayment_plan_response(
    response: CreateLoanApplicationResponse,
    request: Request,
) -> OcenAckResponse:
    """OCEN callback — lender sets repayment plan."""
    if not await _verify_jws(request):
        raise HTTPException(status_code=401, detail="Invalid JWS signature")
    return OcenAckResponse(
        trace_id=response.metadata.trace_id,
        timestamp=response.metadata.timestamp,
    )


@app.get("/health")
async def health() -> dict[str, str | bool]:
    checks: dict[str, bool] = {}

    try:
        temporal = await get_temporal_client()
        checks["temporal"] = temporal is not None
    except Exception:
        checks["temporal"] = False

    return {"status": "ok", "service": "borrower-gateway", **checks}
