"""Borrower Gateway service — manages loan application lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from .models import LoanApplicationRequest, LoanApplicationResponse, LoanApplicationStatus

logger = structlog.get_logger()


class BorrowerGatewayService:
    """Manages loan applications and orchestrates the OCEN flow."""

    def __init__(self) -> None:
        self._applications: dict[uuid.UUID, dict[str, Any]] = {}

    def initiate_application(self, request: LoanApplicationRequest) -> LoanApplicationResponse:
        app_id = uuid.uuid4()
        workflow_id = f"loan-{app_id}"

        self._applications[app_id] = {
            "application_id": app_id,
            "invoice_id": request.invoice_id,
            "vendor_gstin": request.vendor_gstin,
            "anchor_gstin": request.anchor_gstin,
            "amount_requested": request.amount_requested,
            "status": "initiated",
            "current_gate": "d0_kind1",
            "workflow_id": workflow_id,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        logger.info(
            "loan_application_initiated",
            application_id=str(app_id),
            invoice_id=str(request.invoice_id),
            amount=str(request.amount_requested),
        )

        return LoanApplicationResponse(
            application_id=app_id,
            invoice_id=request.invoice_id,
            status="initiated",
            workflow_id=workflow_id,
            message="Loan application initiated. D0 Kind 1 gate evaluation starting.",
        )

    def get_status(self, application_id: uuid.UUID) -> LoanApplicationStatus:
        app = self._applications.get(application_id)
        if not app:
            raise KeyError(f"Application {application_id} not found")

        return LoanApplicationStatus(
            application_id=app["application_id"],
            status=app["status"],
            current_gate=app.get("current_gate"),
            amount_requested=app.get("amount_requested"),
            amount_sanctioned=app.get("amount_sanctioned"),
            lender_id=app.get("lender_id"),
            created_at=app.get("created_at"),
            updated_at=app.get("updated_at"),
        )

    def update_gate(
        self,
        application_id: uuid.UUID,
        gate: str,
        status: str,
        **extra: Any,
    ) -> None:
        app = self._applications.get(application_id)
        if not app:
            raise KeyError(f"Application {application_id} not found")

        app["current_gate"] = gate
        app["status"] = status
        app["updated_at"] = datetime.now(UTC)
        app.update(extra)

        logger.info(
            "gate_updated",
            application_id=str(application_id),
            gate=gate,
            status=status,
        )
