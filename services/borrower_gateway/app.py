"""Borrower Gateway FastAPI application — OCEN loan origination API."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIdMiddleware
from libs.ocen_client.models.journey import (
    CreateLoanApplicationResponse,
    OcenAckResponse,
)
from libs.ocen_client.network_client import OcenNetworkClient

from .models import LoanApplicationRequest, LoanApplicationResponse, LoanApplicationStatus
from .service import BorrowerGatewayService

configure_logging(json_output=True)

app = FastAPI(title="Borrower Gateway - OCEN LA", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)

gateway_service = BorrowerGatewayService()
ocen_client = OcenNetworkClient()


@app.post("/loans/apply", response_model=LoanApplicationResponse)
def apply_for_loan(request: LoanApplicationRequest) -> LoanApplicationResponse:
    return gateway_service.initiate_application(request)


class ApplicationStatusRequest(BaseModel):
    application_id: UUID


@app.post("/loans/status", response_model=LoanApplicationStatus)
def get_loan_status(request: ApplicationStatusRequest) -> LoanApplicationStatus:
    try:
        return gateway_service.get_status(request.application_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post(
    "/v4.0.0alpha/loanApplications/createLoanResponse",
    response_model=OcenAckResponse,
)
async def create_loan_response(
    response: CreateLoanApplicationResponse,
) -> OcenAckResponse:
    """OCEN async callback — lender posts loan decision back to LA."""
    return await ocen_client.handle_loan_response(response)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "borrower-gateway"}
