"""Borrower Gateway service — manages loan application lifecycle.

Supports two backends:
- In-memory (default, for tests and local dev without DB)
- PostgreSQL via SQLAlchemy async (when DB is available)

Toggle via GATEWAY_USE_DB=true environment variable.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from .models import LoanApplicationRequest, LoanApplicationResponse, LoanApplicationStatus

logger = structlog.get_logger()


class BorrowerGatewayService:
    """Manages loan applications — in-memory or DB-backed."""

    def __init__(self) -> None:
        self._applications: dict[uuid.UUID, dict[str, Any]] = {}
        self._idempotency_index: dict[str, uuid.UUID] = {}

    def initiate_application(self, request: LoanApplicationRequest) -> LoanApplicationResponse:
        if request.idempotency_key and request.idempotency_key in self._idempotency_index:
            existing_id = self._idempotency_index[request.idempotency_key]
            app = self._applications[existing_id]
            logger.info("idempotent_request_returned", application_id=str(existing_id))
            return LoanApplicationResponse(
                application_id=existing_id,
                invoice_id=app["invoice_id"],
                status=app["status"],
                workflow_id=app["workflow_id"],
                message="Existing application returned (idempotent).",
            )

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

        if request.idempotency_key:
            self._idempotency_index[request.idempotency_key] = app_id

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


class AsyncDBGatewayService:
    """DB-backed service using SQLAlchemy async sessions."""

    async def initiate_application(
        self, request: LoanApplicationRequest
    ) -> LoanApplicationResponse:
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import LoanApplicationRecord

        async with async_session() as session:
            if request.idempotency_key:
                stmt = select(LoanApplicationRecord).where(
                    LoanApplicationRecord.idempotency_key == request.idempotency_key
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    logger.info("idempotent_request_returned", application_id=str(existing.id))
                    return LoanApplicationResponse(
                        application_id=existing.id,
                        invoice_id=existing.invoice_id,
                        status=existing.status,
                        workflow_id=existing.workflow_id,
                        message="Existing application returned (idempotent).",
                    )

            app_id = uuid.uuid4()
            workflow_id = f"loan-{app_id}"

            record = LoanApplicationRecord(
                id=app_id,
                invoice_id=request.invoice_id,
                vendor_gstin=request.vendor_gstin,
                anchor_gstin=request.anchor_gstin,
                amount_requested=request.amount_requested,
                status="initiated",
                current_gate="d0_kind1",
                workflow_id=workflow_id,
                idempotency_key=request.idempotency_key,
            )
            session.add(record)
            await session.commit()

            logger.info(
                "loan_application_initiated",
                application_id=str(app_id),
                invoice_id=str(request.invoice_id),
            )

            return LoanApplicationResponse(
                application_id=app_id,
                invoice_id=request.invoice_id,
                status="initiated",
                workflow_id=workflow_id,
                message="Loan application initiated. D0 Kind 1 gate evaluation starting.",
            )

    async def get_status(self, application_id: uuid.UUID) -> LoanApplicationStatus:
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import LoanApplicationRecord

        async with async_session() as session:
            stmt = select(LoanApplicationRecord).where(LoanApplicationRecord.id == application_id)
            record = (await session.execute(stmt)).scalar_one_or_none()
            if not record:
                raise KeyError(f"Application {application_id} not found")

            return LoanApplicationStatus(
                application_id=record.id,
                status=record.status,
                current_gate=record.current_gate,
                amount_requested=record.amount_requested,
                amount_sanctioned=record.amount_sanctioned,
                lender_id=record.selected_lender_id,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

    async def update_gate(
        self,
        application_id: uuid.UUID,
        gate: str,
        status: str,
        **extra: Any,
    ) -> None:
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import LoanApplicationRecord

        async with async_session() as session:
            stmt = select(LoanApplicationRecord).where(LoanApplicationRecord.id == application_id)
            record = (await session.execute(stmt)).scalar_one_or_none()
            if not record:
                raise KeyError(f"Application {application_id} not found")

            record.current_gate = gate
            record.status = status
            if "amount_sanctioned" in extra:
                record.amount_sanctioned = extra["amount_sanctioned"]
            if "selected_lender_id" in extra:
                record.selected_lender_id = extra["selected_lender_id"]
            if "offer_data" in extra:
                record.offer_data = extra["offer_data"]

            await session.commit()
            logger.info(
                "gate_updated", application_id=str(application_id), gate=gate, status=status
            )


def get_gateway_service() -> BorrowerGatewayService | AsyncDBGatewayService:
    if os.environ.get("GATEWAY_USE_DB", "false").lower() == "true":
        return AsyncDBGatewayService()
    return BorrowerGatewayService()
