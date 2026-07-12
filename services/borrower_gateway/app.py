"""Borrower Gateway FastAPI application — OCEN loan origination API."""

from __future__ import annotations

import os
from uuid import UUID  # noqa: TC003

import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from temporalio.client import Client as TemporalClient

from libs.auth.factory import get_borrower_verifier
from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware, DPDPRBACMiddleware
from libs.common.rate_limit import RateLimitMiddleware
from libs.common.tracing import init_tracing
from libs.common.webhook_auth import verify_hmac_signature
from libs.ocen_client.jws.signer import OcenJWSSigner
from libs.ocen_client.models.journey import (
    CreateLoanApplicationResponse,
    OcenAckResponse,
)
from libs.ocen_client.network_client import OcenNetworkClient

from .dpdp_api import dpdp_router
from .models import (
    InvoiceCapturedRequest,
    InvoiceCapturedResponse,
    LoanApplicationRequest,
    LoanApplicationResponse,
    LoanApplicationStatus,
)
from .ops_api import ops_router, vendors_router
from .service import get_gateway_service

configure_logging(json_output=True)
init_tracing(service_name="borrower-gateway")
logger = structlog.get_logger()

INTEGRATION_MODE = os.environ.get("INTEGRATION_MODE", "")
BACKOFFICE_WEBHOOK_SECRET = os.environ.get("BACKOFFICE_WEBHOOK_SECRET", "")

# Borrower ownership enforcement — off by default because it requires a live
# Kratos+Hydra deployment to issue vendors real tokens (see Phase 3 of the
# RBAC/role-UIs plan and docs/borrower-ciam-contract.md). Flip on once that
# infrastructure is deployed; until then /loans/* stays open, matching
# today's behavior, rather than locking borrowers out with no way to
# authenticate.
BORROWER_AUTH_ENABLED = os.environ.get("BORROWER_AUTH_ENABLED", "false").lower() == "true"

app = FastAPI(title="Borrower Gateway - OCEN LA", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(DPDPRBACMiddleware)
app.add_middleware(RateLimitMiddleware)
app.include_router(ops_router)
app.include_router(vendors_router)
app.include_router(dpdp_router)

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


async def _get_borrower_claims(request: Request):
    """Resolve the calling vendor's identity from a Hydra-issued Bearer token.

    Returns None when BORROWER_AUTH_ENABLED=false (today's default — no
    Kratos/Hydra deployed yet). Once enabled, requires a valid token and
    returns its TokenClaims so callers can enforce ownership.
    """
    if not BORROWER_AUTH_ENABLED:
        return None

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    from libs.auth.adapters.kratos import AuthenticationError

    try:
        token = auth_header.removeprefix("Bearer ")
        return await get_borrower_verifier().verify(token)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@app.post("/loans/apply", response_model=LoanApplicationResponse)
async def apply_for_loan(
    request: LoanApplicationRequest, http_request: Request
) -> LoanApplicationResponse:
    claims = await _get_borrower_claims(http_request)
    if claims is not None and claims.raw.get("gstin") != request.vendor_gstin:
        raise HTTPException(
            status_code=403,
            detail="Cannot submit a loan application for a different vendor GSTIN.",
        )

    response = gateway_service.initiate_application(request)

    try:
        temporal = await get_temporal_client()
        from services.la_orchestrator.workflows import LoanOriginationInput

        workflow_input = LoanOriginationInput(
            loan_application_id=str(response.application_id),
            data_principal_id=request.vendor_gstin,
            vendor_gstin=request.vendor_gstin,
        )
        await temporal.start_workflow(
            "LoanOriginationWorkflow",
            workflow_input,
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
async def get_loan_status(
    request: ApplicationStatusRequest, http_request: Request
) -> LoanApplicationStatus:
    claims = await _get_borrower_claims(http_request)

    try:
        status = gateway_service.get_status(request.application_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if claims is not None and claims.raw.get("gstin") != status.vendor_gstin:
        raise HTTPException(status_code=403, detail="Not your application.")

    return status


# ─── Invoice Capture (ERP Connector) ───────────────────────


@app.post("/invoices/captured", response_model=InvoiceCapturedResponse)
async def capture_invoice(
    request: InvoiceCapturedRequest, http_request: Request
) -> InvoiceCapturedResponse:
    """Receive invoice notification from ERP connector (ERPNext/Frappe).

    Verified via inbound HMAC signature (X-Platform-Signature header, same
    BACKOFFICE_WEBHOOK_SECRET and scheme used for outbound delivery in
    services/backoffice_sync/webhook_client.py). Skipped only in sandbox mode.
    """
    import uuid

    if INTEGRATION_MODE != "sandbox":
        signature = http_request.headers.get("x-platform-signature")
        body = await http_request.body()
        if not verify_hmac_signature(BACKOFFICE_WEBHOOK_SECRET, body, signature):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook signature")

    invoice_id = uuid.uuid4()
    logger.info(
        "invoice_captured",
        invoice_id=str(invoice_id),
        irn=request.irn[:16] + "...",
        vendor_gstin=request.vendor_gstin,
        anchor_gstin=request.anchor_gstin,
        amount=str(request.amount),
    )

    return InvoiceCapturedResponse(
        invoice_id=invoice_id,
        irn=request.irn,
        status="captured",
        message="Invoice captured. Ready for loan application.",
    )


# ─── OCEN Network Callback Endpoints ───────────────────────────


async def _verify_jws(request: Request) -> bool:
    """Verify inbound JWS signature from lender.

    A missing signature is only tolerated in INTEGRATION_MODE=sandbox (local
    dev / simulated lender flows). Outside sandbox, an unsigned callback is
    always rejected.
    """
    signature = request.headers.get("x-jws-signature")
    if not signature:
        return INTEGRATION_MODE == "sandbox"
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


@app.get("/brand")
async def get_brand() -> dict:
    """Brand config for PWA/frontend theming. Reads from brand.yaml."""
    from brand.brand import load_brand

    b = load_brand()
    return {
        "name": b.identity.name,
        "tagline": b.identity.tagline,
        "back_office": {
            "name": b.back_office.name,
            "short_name": b.back_office.short_name,
        },
        "colors": b.colors.model_dump(),
        "typography": {
            "font_ui": b.typography.font_ui,
            "font_mono": b.typography.font_mono,
            "google_fonts_url": b.typography.google_fonts_url,
            "weights": b.typography.weights,
            "sizes": b.typography.sizes,
        },
        "shape": b.shape.model_dump(),
    }


@app.get("/health")
async def health() -> dict[str, str | bool]:
    checks: dict[str, bool] = {}

    try:
        temporal = await get_temporal_client()
        checks["temporal"] = temporal is not None
    except Exception:
        checks["temporal"] = False

    return {"status": "ok", "service": "borrower-gateway", **checks}
