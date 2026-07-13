"""DPDP Rights API — endpoints for data principal rights and consent management.

Protected by RBAC when DPDP_RBAC_ENABLED=true (platform-admin role required).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from temporalio.client import Client as TemporalClient

from libs.common.models import REQUIRED_CONSENT_PURPOSES

logger = structlog.get_logger()

dpdp_router = APIRouter(prefix="/dpdp", tags=["dpdp"])

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")

_temporal_client: TemporalClient | None = None


async def _get_temporal_client() -> TemporalClient:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await TemporalClient.connect(
            TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE
        )
    return _temporal_client


# ─── Request/Response Models ──────────────────────────────────


class DSRSubmitRequest(BaseModel):
    data_principal_id: str
    right_type: str  # access, erasure, correction, grievance, nomination


class DSRSubmitResponse(BaseModel):
    request_id: str
    status: str
    sla_deadline: str
    workflow_id: str


class DSRStatusResponse(BaseModel):
    request_id: str
    status: str
    right_type: str
    sla_deadline: str
    completed_at: str | None = None


class ConsentStatusResponse(BaseModel):
    data_principal_id: str
    consents: list[dict]


class DecisionReceiptEntry(BaseModel):
    id: str
    gate: str
    outcome: str
    ruleset_hash: str
    input_hash: str
    engine_version: str
    signature: str | None
    chain_hash: str | None
    evaluated_at: str


class AuditReceiptChainResponse(BaseModel):
    loan_application_id: str
    receipts: list[DecisionReceiptEntry]
    chain_verified: bool


# ─── DSR Endpoints ────────────────────────────────────────────


@dpdp_router.post("/rights/submit", response_model=DSRSubmitResponse)
async def submit_dsr(request: DSRSubmitRequest) -> DSRSubmitResponse:
    """Submit a Data Subject Rights request (access, erasure, correction)."""
    valid_types = {"access", "erasure", "correction", "grievance", "nomination"}
    if request.right_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid right_type. Must be one of: {', '.join(sorted(valid_types))}",
        )

    request_id = str(uuid.uuid4())
    sla_deadline = datetime.now(UTC) + timedelta(hours=72)
    workflow_id = f"dsr-{request.right_type}-{request_id}"

    try:
        temporal = await _get_temporal_client()

        from services.la_orchestrator.workflows import DSRWorkflowInput

        workflow_input = DSRWorkflowInput(
            request_id=request_id,
            data_principal_id=request.data_principal_id,
            right_type=request.right_type,
        )

        await temporal.start_workflow(
            "DSRFulfillmentWorkflow",
            workflow_input,
            id=workflow_id,
            task_queue=os.environ.get("TEMPORAL_TASK_QUEUE", "loan-origination"),
        )
        logger.info(
            "dsr_workflow_started",
            request_id=request_id,
            right_type=request.right_type,
        )
    except Exception as e:
        logger.error("dsr_workflow_start_failed", error=str(e), request_id=request_id)
        raise HTTPException(status_code=500, detail="Failed to start DSR workflow") from e

    return DSRSubmitResponse(
        request_id=request_id,
        status="submitted",
        sla_deadline=sla_deadline.isoformat(),
        workflow_id=workflow_id,
    )


@dpdp_router.get("/rights/{request_id}", response_model=DSRStatusResponse)
async def get_dsr_status(request_id: str) -> DSRStatusResponse:
    """Check the status of a DSR request."""
    try:
        temporal = await _get_temporal_client()
        # Try all right types to find the workflow
        for right_type in ("access", "erasure", "correction", "grievance", "nomination"):
            workflow_id = f"dsr-{right_type}-{request_id}"
            try:
                handle = temporal.get_workflow_handle(workflow_id)
                desc = await handle.describe()
                status = desc.status.name if desc.status else "running"

                return DSRStatusResponse(
                    request_id=request_id,
                    status=status,
                    right_type=right_type,
                    sla_deadline=(datetime.now(UTC) + timedelta(hours=72)).isoformat(),
                )
            except Exception:
                continue

    except Exception as e:
        logger.error("dsr_status_check_failed", error=str(e))

    raise HTTPException(status_code=404, detail=f"DSR request {request_id} not found")


# ─── Consent Endpoints ────────────────────────────────────────


@dpdp_router.get("/consent/{data_principal_id}", response_model=ConsentStatusResponse)
async def get_consent_status(data_principal_id: str) -> ConsentStatusResponse:
    """Get all consent records for a data principal."""
    from libs.integrations.factory import get_consent_client

    consent_client = get_consent_client()
    result = await consent_client.check_consent(
        data_principal_id=data_principal_id,
        purposes=REQUIRED_CONSENT_PURPOSES,
    )

    return ConsentStatusResponse(
        data_principal_id=data_principal_id,
        consents=[
            {
                "purposes": REQUIRED_CONSENT_PURPOSES,
                "allowed": result.allowed,
                "reason": result.reason,
            }
        ],
    )


# ─── Audit Endpoints ──────────────────────────────────────────


@dpdp_router.get("/audit/receipts/{loan_application_id}", response_model=AuditReceiptChainResponse)
async def get_receipt_chain(loan_application_id: uuid.UUID) -> AuditReceiptChainResponse:
    """Signed decision receipt chain for a loan application — the audit
    trail an admin/auditor uses to verify every D0-D3 decision actually
    happened, wasn't tampered with, and links to the one before it.

    This is the only way to see this today besides a raw DB query —
    services/la_orchestrator/activities.py::evaluate_decision creates and
    signs these receipts, but nothing surfaced them until now.
    """
    from sqlalchemy import select

    from libs.audit.receipts import ChainVerifier
    from libs.common.models import DecisionGate, DecisionOutcome, DecisionReceipt
    from libs.db.engine import async_session
    from libs.db.models import DecisionReceiptRecord

    async with async_session() as session:
        rows = (
            (
                await session.execute(
                    select(DecisionReceiptRecord)
                    .where(DecisionReceiptRecord.loan_application_id == loan_application_id)
                    .order_by(DecisionReceiptRecord.evaluated_at.asc())
                )
            )
            .scalars()
            .all()
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No decision receipts found for loan application {loan_application_id}.",
        )

    receipts = [
        DecisionReceipt(
            id=row.id,
            loan_application_id=row.loan_application_id,
            gate=DecisionGate(row.gate),
            outcome=DecisionOutcome(row.outcome),
            ruleset_hash=row.ruleset_hash,
            input_hash=row.input_hash,
            output=row.output_data or {},
            engine_version=row.engine_version,
            signature=row.signature,
            chain_hash=row.chain_hash,
            evaluated_at=row.evaluated_at,
        )
        for row in rows
    ]

    return AuditReceiptChainResponse(
        loan_application_id=str(loan_application_id),
        receipts=[
            DecisionReceiptEntry(
                id=str(r.id),
                gate=r.gate.value,
                outcome=r.outcome.value,
                ruleset_hash=r.ruleset_hash,
                input_hash=r.input_hash,
                engine_version=r.engine_version,
                signature=r.signature,
                chain_hash=r.chain_hash,
                evaluated_at=r.evaluated_at.isoformat(),
            )
            for r in receipts
        ],
        chain_verified=ChainVerifier.verify_chain(receipts),
    )
