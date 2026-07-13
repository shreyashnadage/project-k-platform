"""Ops Command API — endpoints for the ops back-office to command the platform.

Auth: Bearer API key validated via middleware.
"""

from __future__ import annotations

import inspect
import os
import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException

from libs.common.events import EventMetadata, EventType, TradeEvent

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
    UdyamVerifyRequest,
    UdyamVerifyResponse,
    VendorActivateRequest,
    VendorInviteRequest,
    VendorInviteResponse,
    VendorRegisterRequest,
    VendorRegisterResponse,
)

logger = structlog.get_logger()

ops_router = APIRouter(prefix="/ops", tags=["ops"])
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])

_DEFAULT_OPS_API_KEY = "dev-ops-key-change-in-production"
OPS_API_KEY = os.environ.get("OPS_API_KEY", _DEFAULT_OPS_API_KEY)
PLATFORM_BASE_URL = os.environ.get("PLATFORM_BASE_URL", "http://localhost:8000")

# Transitional shared-secret auth for /ops/* — replaced by real per-user
# Keycloak tokens once the Platform Console ships (see Phase 3 of the
# RBAC/role-UIs plan). Defaults to enabled so existing ops workflows keep
# working; flip to "false" once every caller has migrated to a verified
# per-user Bearer token.
OPS_API_KEY_FALLBACK_ENABLED = (
    os.environ.get("OPS_API_KEY_FALLBACK_ENABLED", "true").lower() == "true"
)

if (
    OPS_API_KEY_FALLBACK_ENABLED
    and OPS_API_KEY == _DEFAULT_OPS_API_KEY
    and os.environ.get("INTEGRATION_MODE", "") != "sandbox"
):
    raise RuntimeError(
        "OPS_API_KEY is not set, and the known dev-only default "
        f"({_DEFAULT_OPS_API_KEY!r}) would be accepted as a valid Bearer "
        "credential for every /ops/* endpoint outside INTEGRATION_MODE=sandbox. "
        "Set OPS_API_KEY explicitly, set OPS_API_KEY_FALLBACK_ENABLED=false, "
        "or set INTEGRATION_MODE=sandbox for local development."
    )


def _emit_event(
    event_type: EventType,
    entity_id: uuid.UUID,
    entity_type: str = "loan",
    payload: dict | None = None,
    actor_id: str | None = None,
) -> None:
    """Emit an ops event to Redpanda. Best-effort — does not block the response."""
    try:
        from libs.common.event_producer import EventProducer

        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
        producer = EventProducer(bootstrap_servers=bootstrap)
        event = TradeEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=entity_id,
            payload=payload or {},
            metadata=EventMetadata(source_service="borrower-gateway", actor_id=actor_id),
        )
        producer.publish(event)
        producer.flush(timeout=2.0)
    except Exception as e:
        logger.warning("ops_event_emission_failed", event_type=event_type.value, error=str(e))


async def verify_ops_api_key(authorization: str = Header(...)) -> str:
    """Validate Bearer API key for ops endpoints.

    Transitional auth — see OPS_API_KEY_FALLBACK_ENABLED above.
    """
    if not OPS_API_KEY_FALLBACK_ENABLED:
        raise HTTPException(
            status_code=401,
            detail="Shared ops API key auth is disabled. Use a per-user Keycloak token.",
        )
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

        _emit_event(
            EventType.OPS_HOLD_APPLIED,
            entity_id=request.application_id,
            payload={"reason": request.reason, "held_by": request.held_by},
            actor_id=request.held_by,
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

        _emit_event(
            EventType.OPS_HOLD_RELEASED,
            entity_id=request.application_id,
            payload={"released_by": request.released_by},
            actor_id=request.released_by,
        )

        return OpsCommandResponse(
            success=True,
            application_id=request.application_id,
            action="release",
            message="Application released from hold.",
        )
    except Exception as e:
        logger.error("ops_release_failed", error=str(e), application_id=str(request.application_id))
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

    _emit_event(
        EventType.OPS_FLAG_ADDED,
        entity_id=request.application_id,
        payload={
            "flag_type": request.flag_type,
            "note": request.note,
            "flagged_by": request.flagged_by,
        },
        actor_id=request.flagged_by,
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

    _emit_event(
        EventType.OPS_ESCALATED,
        entity_id=request.application_id,
        payload={"reason": request.reason, "escalated_by": request.escalated_by},
        actor_id=request.escalated_by,
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
        result = service.get_status(application_id)
        status = await result if inspect.isawaitable(result) else result
        return OpsApplicationDetail(
            application_id=status.application_id,
            vendor_gstin=status.vendor_gstin or "",
            # anchor_gstin isn't tracked on LoanApplicationStatus at all yet —
            # still a known gap, not something this fix addresses.
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


def _use_db() -> bool:
    """Mirrors services/borrower_gateway/service.py's GATEWAY_USE_DB toggle —
    same flag, same default (off), so both the loan-application path and
    the vendor/anchor onboarding path switch to real persistence together."""
    return os.environ.get("GATEWAY_USE_DB", "false").lower() == "true"


@ops_router.post("/vendor/invite", response_model=VendorInviteResponse)
async def invite_vendor(
    request: VendorInviteRequest,
    _: str = Depends(verify_ops_api_key),
) -> VendorInviteResponse:
    """Create a pending vendor record and generate invite token."""
    invite_token = secrets.token_urlsafe(32)
    invite_link = f"{PLATFORM_BASE_URL}/invite/{invite_token}"

    if _use_db():
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import VendorRecord

        async with async_session() as session:
            existing = (
                await session.execute(
                    select(VendorRecord).where(VendorRecord.gstin == request.gstin)
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"A vendor with GSTIN {request.gstin} already exists "
                        f"(status={existing.status})."
                    ),
                )

            vendor_id = uuid.uuid4()
            session.add(
                VendorRecord(
                    id=vendor_id,
                    name=request.name,
                    gstin=request.gstin,
                    phone=request.phone,
                    invite_token=invite_token,
                    status="pending",
                    invited_by=request.invited_by,
                )
            )
            await session.commit()
    else:
        vendor_id = uuid.uuid4()

    logger.info(
        "vendor_invited",
        vendor_id=str(vendor_id),
        gstin=request.gstin,
        invited_by=request.invited_by,
    )

    _emit_event(
        EventType.VENDOR_INVITED,
        entity_id=vendor_id,
        entity_type="vendor",
        payload={"gstin": request.gstin, "invited_by": request.invited_by},
        actor_id=request.invited_by,
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
    if _use_db():
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import AnchorRecord

        async with async_session() as session:
            existing = (
                await session.execute(
                    select(AnchorRecord).where(AnchorRecord.gstin == request.gstin)
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"An anchor with GSTIN {request.gstin} already exists.",
                )

            anchor_id = uuid.uuid4()
            session.add(
                AnchorRecord(
                    id=anchor_id,
                    name=request.name,
                    gstin=request.gstin,
                    sector=request.sector,
                    region=request.region,
                )
            )
            await session.commit()
    else:
        anchor_id = uuid.uuid4()

    logger.info(
        "anchor_onboarded",
        anchor_id=str(anchor_id),
        gstin=request.gstin,
        name=request.name,
        onboarded_by=request.onboarded_by,
    )

    _emit_event(
        EventType.ANCHOR_ONBOARDED,
        entity_id=anchor_id,
        entity_type="anchor",
        payload={"gstin": request.gstin, "name": request.name},
        actor_id=request.onboarded_by,
    )

    return AnchorOnboardResponse(
        anchor_id=anchor_id,
        status="onboarded",
        message=f"Anchor '{request.name}' onboarded successfully.",
    )


# ─── Udyam Verification ──────────────────────────────────────


@vendors_router.post("/verify-udyam", response_model=UdyamVerifyResponse)
async def verify_udyam(request: UdyamVerifyRequest) -> UdyamVerifyResponse:
    """Verify Udyam number and return enterprise details for auto-population."""
    from libs.integrations.factory import get_udyam_client

    client = get_udyam_client()
    result = await client.verify(request.udyam_number)

    logger.info(
        "udyam_verified",
        udyam_number=request.udyam_number[:10] + "***",
        valid=result.valid,
        enterprise_type=result.enterprise_type,
    )

    return UdyamVerifyResponse(
        valid=result.valid,
        udyam_number=result.udyam_number,
        enterprise_name=result.enterprise_name,
        enterprise_type=result.enterprise_type,
        major_activity=result.major_activity,
        organization_type=result.organization_type,
        date_of_incorporation=result.date_of_incorporation,
        state=result.state,
        district=result.district,
        city=result.city,
        pincode=result.pincode,
        address=result.address,
        nic_codes=result.nic_codes,
        owner_name=result.owner_name,
    )


# ─── Vendor Self-Registration (PWA) ────────────────────────────


@vendors_router.post("/register", response_model=VendorRegisterResponse)
async def register_vendor(request: VendorRegisterRequest) -> VendorRegisterResponse:
    """Vendor self-registration from PWA. No auth required (public endpoint).

    If udyam_number is provided, auto-verifies and populates enterprise data.
    """
    udyam_data: dict = {}

    if request.udyam_number:
        from libs.integrations.factory import get_udyam_client

        client = get_udyam_client()
        result = await client.verify(request.udyam_number)
        if result.valid:
            udyam_data = {
                "enterprise_name": result.enterprise_name,
                "enterprise_type": result.enterprise_type,
                "udyam_category": result.enterprise_type,
                "address": result.address,
                "state": result.state,
                "district": result.district,
                "city": result.city,
                "pincode": result.pincode,
                "nic_codes": result.nic_codes,
                "owner_name": result.owner_name,
            }

    if _use_db():
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import VendorRecord

        async with async_session() as session:
            existing = (
                await session.execute(
                    select(VendorRecord).where(VendorRecord.gstin == request.gstin)
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"A vendor with GSTIN {request.gstin} already exists "
                        f"(status={existing.status})."
                    ),
                )

            vendor_id = uuid.uuid4()
            session.add(
                VendorRecord(
                    id=vendor_id,
                    name=request.name,
                    gstin=request.gstin,
                    phone=request.phone,
                    udyam_number=request.udyam_number,
                    udyam_category=udyam_data.get("udyam_category") or request.udyam_category,
                    status="active",
                )
            )
            await session.commit()
    else:
        vendor_id = uuid.uuid4()

    logger.info(
        "vendor_self_registered",
        vendor_id=str(vendor_id),
        gstin=request.gstin,
        name=request.name,
        udyam_verified=bool(udyam_data),
    )

    _emit_event(
        EventType.VENDOR_ONBOARDED,
        entity_id=vendor_id,
        entity_type="vendor",
        payload={
            "gstin": request.gstin,
            "name": request.name,
            "source": "pwa_self_register",
            **udyam_data,
        },
    )

    return VendorRegisterResponse(
        vendor_id=vendor_id,
        status="active",
        message="Registration successful. You can now apply for loans.",
    )


@vendors_router.post("/activate", response_model=VendorRegisterResponse)
async def activate_vendor(request: VendorActivateRequest) -> VendorRegisterResponse:
    """Complete an invited vendor's registration (from PWA invite flow)."""
    if _use_db():
        from sqlalchemy import select

        from libs.db.engine import async_session
        from libs.db.models import VendorRecord

        async with async_session() as session:
            vendor = (
                await session.execute(
                    select(VendorRecord).where(VendorRecord.invite_token == request.invite_token)
                )
            ).scalar_one_or_none()
            if vendor is None:
                raise HTTPException(status_code=404, detail="Invite token not found or expired.")
            if vendor.status == "active":
                raise HTTPException(
                    status_code=422, detail="This invite has already been activated."
                )

            vendor.status = "active"
            vendor.invite_token = None  # one-time use
            if request.name:
                vendor.name = request.name
            if request.udyam_number:
                vendor.udyam_number = request.udyam_number
            if request.udyam_category:
                vendor.udyam_category = request.udyam_category
            await session.commit()
            vendor_id = vendor.id
    else:
        vendor_id = uuid.uuid4()

    logger.info(
        "vendor_activated",
        vendor_id=str(vendor_id),
        invite_token=request.invite_token[:8] + "...",
    )

    _emit_event(
        EventType.VENDOR_ACTIVATED,
        entity_id=vendor_id,
        entity_type="vendor",
        payload={"source": "pwa_invite_activation"},
    )

    return VendorRegisterResponse(
        vendor_id=vendor_id,
        status="active",
        message="Account activated. You can now apply for loans.",
    )
