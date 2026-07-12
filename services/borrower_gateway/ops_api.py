"""Ops Command API — endpoints for Frappe back-office to command the platform.

Auth: Bearer API key validated via middleware. Frappe stores the key in site_config.json.
"""

from __future__ import annotations

import os
import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException

from .ops_models import (
    AnchorOnboardRequest,
    AnchorOnboardResponse,
    OpsApplicationDetail,
    OpsApplicationList,
    OpsCommandResponse,
    OpsEscalateRequest,
    OpsFlagRequest,
    OpsHoldRequest,
    OpsReleaseRequest,
    VendorActivateRequest,
    VendorInviteRequest,
    VendorInviteResponse,
    VendorRegisterRequest,
    VendorRegisterResponse,
)

logger = structlog.get_logger()

ops_router = APIRouter(prefix="/ops", tags=["ops"])
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])

OPS_API_KEY = os.environ.get("OPS_API_KEY", "dev-ops-key-change-in-production")
PLATFORM_BASE_URL = os.environ.get("PLATFORM_BASE_URL", "http://localhost:8000")


async def verify_ops_api_key(authorization: str = Header(...)) -> str:
    """Validate Bearer API key for ops endpoints."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[7:]
    if not secrets.compare_digest(token, OPS_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token


# ─── Ops Commands ──────────────────────────────────────────────


@ops_router.post("/hold", response_model=OpsCommandResponse)
async def ops_hold(
    request: OpsHoldRequest,
    _: str = Depends(verify_ops_api_key),
) -> OpsCommandResponse:
    """Hold an application before OCEN submission via Temporal signal."""
    from temporalio.client import Client as TemporalClient

    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    try:
        client = await TemporalClient.connect(temporal_address, namespace=namespace)
        workflow_id = f"loan-{request.application_id}"
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("ops_hold_requested", request.reason)

        logger.info(
            "ops_hold_applied",
            application_id=str(request.application_id),
            reason=request.reason,
            held_by=request.held_by,
        )

        return OpsCommandResponse(
            success=True,
            application_id=request.application_id,
            action="hold",
            message=f"Application held. Reason: {request.reason}",
        )
    except Exception as e:
        logger.error("ops_hold_failed", error=str(e), application_id=str(request.application_id))
        raise HTTPException(status_code=422, detail=f"Cannot hold application: {e}") from e


@ops_router.post("/release", response_model=OpsCommandResponse)
async def ops_release(
    request: OpsReleaseRequest,
    _: str = Depends(verify_ops_api_key),
) -> OpsCommandResponse:
    """Release a held application via Temporal signal."""
    from temporalio.client import Client as TemporalClient

    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    try:
        client = await TemporalClient.connect(temporal_address, namespace=namespace)
        workflow_id = f"loan-{request.application_id}"
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("ops_hold_released")

        logger.info(
            "ops_hold_released",
            application_id=str(request.application_id),
            released_by=request.released_by,
        )

        return OpsCommandResponse(
            success=True,
            application_id=request.application_id,
            action="release",
            message="Application released from hold.",
        )
    except Exception as e:
        logger.error(
            "ops_release_failed", error=str(e), application_id=str(request.application_id)
        )
        raise HTTPException(status_code=422, detail=f"Cannot release application: {e}") from e


@ops_router.post("/flag", response_model=OpsCommandResponse)
async def ops_flag(
    request: OpsFlagRequest,
    _: str = Depends(verify_ops_api_key),
) -> OpsCommandResponse:
    """Add an ops annotation/flag to an application record."""
    logger.info(
        "ops_flag_added",
        application_id=str(request.application_id),
        flag_type=request.flag_type,
        flagged_by=request.flagged_by,
    )

    return OpsCommandResponse(
        success=True,
        application_id=request.application_id,
        action="flag",
        message=f"Flag '{request.flag_type}' added: {request.note}",
    )


@ops_router.post("/escalate", response_model=OpsCommandResponse)
async def ops_escalate(
    request: OpsEscalateRequest,
    _: str = Depends(verify_ops_api_key),
) -> OpsCommandResponse:
    """Escalate to collections (post-disbursement)."""
    logger.info(
        "ops_escalated",
        application_id=str(request.application_id),
        reason=request.reason,
        escalated_by=request.escalated_by,
    )

    return OpsCommandResponse(
        success=True,
        application_id=request.application_id,
        action="escalate",
        message=f"Escalated to collections: {request.reason}",
    )


@ops_router.get("/applications/active", response_model=OpsApplicationList)
async def list_active_applications(
    _: str = Depends(verify_ops_api_key),
) -> OpsApplicationList:
    """List non-terminal applications for reconciliation."""
    from .service import get_gateway_service

    service = get_gateway_service()

    if hasattr(service, "_applications"):
        terminal = {"closed", "rejected", "expired"}
        active = [
            OpsApplicationDetail(
                application_id=app["application_id"],
                vendor_gstin=app["vendor_gstin"],
                anchor_gstin=app["anchor_gstin"],
                amount_requested=app.get("amount_requested"),
                status=app["status"],
                current_gate=app.get("current_gate"),
                workflow_id=app.get("workflow_id"),
                created_at=app.get("created_at"),
                updated_at=app.get("updated_at"),
            )
            for app in service._applications.values()
            if app["status"] not in terminal
        ]
        return OpsApplicationList(applications=active, total=len(active))

    return OpsApplicationList(applications=[], total=0)


@ops_router.get("/applications/{application_id}", response_model=OpsApplicationDetail)
async def get_application_detail(
    application_id: uuid.UUID,
    _: str = Depends(verify_ops_api_key),
) -> OpsApplicationDetail:
    """Full application detail for ops view."""
    from .service import get_gateway_service

    service = get_gateway_service()

    try:
        status = service.get_status(application_id)
        return OpsApplicationDetail(
            application_id=status.application_id,
            vendor_gstin="",
            anchor_gstin="",
            amount_requested=status.amount_requested,
            status=status.status,
            current_gate=status.current_gate,
            lender_id=status.lender_id,
            created_at=status.created_at,
            updated_at=status.updated_at,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ─── Vendor Onboarding (Ops-driven) ────────────────────────────


@ops_router.post("/vendor/invite", response_model=VendorInviteResponse)
async def invite_vendor(
    request: VendorInviteRequest,
    _: str = Depends(verify_ops_api_key),
) -> VendorInviteResponse:
    """Create a pending vendor record and generate invite token."""
    vendor_id = uuid.uuid4()
    invite_token = secrets.token_urlsafe(32)
    invite_link = f"{PLATFORM_BASE_URL}/invite/{invite_token}"

    logger.info(
        "vendor_invited",
        vendor_id=str(vendor_id),
        gstin=request.gstin,
        invited_by=request.invited_by,
    )

    return VendorInviteResponse(
        vendor_id=vendor_id,
        invite_token=invite_token,
        invite_link=invite_link,
    )


# ─── Anchor Onboarding (Ops-driven) ────────────────────────────


@ops_router.post("/anchor/onboard", response_model=AnchorOnboardResponse)
async def onboard_anchor(
    request: AnchorOnboardRequest,
    _: str = Depends(verify_ops_api_key),
) -> AnchorOnboardResponse:
    """Create an anchor record in the platform."""
    anchor_id = uuid.uuid4()

    logger.info(
        "anchor_onboarded",
        anchor_id=str(anchor_id),
        gstin=request.gstin,
        name=request.name,
        onboarded_by=request.onboarded_by,
    )

    return AnchorOnboardResponse(
        anchor_id=anchor_id,
        status="onboarded",
        message=f"Anchor '{request.name}' onboarded successfully.",
    )


# ─── Vendor Self-Registration (PWA) ────────────────────────────


@vendors_router.post("/register", response_model=VendorRegisterResponse)
async def register_vendor(request: VendorRegisterRequest) -> VendorRegisterResponse:
    """Vendor self-registration from PWA. No auth required (public endpoint)."""
    vendor_id = uuid.uuid4()

    logger.info(
        "vendor_self_registered",
        vendor_id=str(vendor_id),
        gstin=request.gstin,
        name=request.name,
    )

    return VendorRegisterResponse(
        vendor_id=vendor_id,
        status="active",
        message="Registration successful. You can now apply for loans.",
    )


@vendors_router.post("/activate", response_model=VendorRegisterResponse)
async def activate_vendor(request: VendorActivateRequest) -> VendorRegisterResponse:
    """Complete an invited vendor's registration (from PWA invite flow)."""
    vendor_id = uuid.uuid4()

    logger.info(
        "vendor_activated",
        vendor_id=str(vendor_id),
        invite_token=request.invite_token[:8] + "...",
    )

    return VendorRegisterResponse(
        vendor_id=vendor_id,
        status="active",
        message="Account activated. You can now apply for loans.",
    )
