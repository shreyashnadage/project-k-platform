"""SQLAlchemy ORM models for the OCEN platform."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal  # noqa: TC003

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LoanApplicationRecord(Base):
    __tablename__ = "loan_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vendor_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    anchor_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    amount_requested: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created")
    current_gate: Mapped[str | None] = mapped_column(String(50))
    workflow_id: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    matched_lender_ids: Mapped[dict | None] = mapped_column(JSONB)
    selected_lender_id: Mapped[str | None] = mapped_column(String(100))
    offer_data: Mapped[dict | None] = mapped_column(JSONB)
    amount_sanctioned: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # DPDP Phase 2: encrypted PII columns (dual-write during transition)
    vendor_gstin_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    vendor_gstin_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anchor_gstin_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    anchor_gstin_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aa_consent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_loan_app_vendor", "vendor_gstin"),
        Index("ix_loan_app_anchor", "anchor_gstin"),
        Index("ix_loan_app_status", "status"),
        Index("ix_loan_app_idempotency", "idempotency_key", unique=True),
    )


class DecisionReceiptRecord(Base):
    __tablename__ = "decision_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    gate: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    ruleset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_data: Mapped[dict | list | None] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(String(20), default="zen-1.0")
    signature: Mapped[str | None] = mapped_column(Text)
    chain_hash: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_receipt_loan_gate", "loan_application_id", "gate"),)


class AnchorRecord(Base):
    __tablename__ = "anchors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    repayment_routing_active: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # DPDP Phase 2: encrypted PII columns (dual-write during transition)
    name_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gstin_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gstin_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)


class VendorRecord(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    udyam_number: Mapped[str | None] = mapped_column(String(30))
    udyam_category: Mapped[str | None] = mapped_column(String(10))
    onboarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # DPDP Phase 2: encrypted PII columns (dual-write during transition)
    name_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gstin_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gstin_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    udyam_number_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    udyam_number_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Vendor invite/activation tracking (migration 006)
    phone: Mapped[str | None] = mapped_column(String(13), nullable=True)
    phone_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    phone_idx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    invited_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    response_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC).replace(hour=23, minute=59, second=59),
    )


# ─── DPDP Compliance Tables ──────────────────────────────────────────


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_principal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    consent_domain: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_method: Mapped[str] = mapped_column(String(30), nullable=False)
    aa_consent_id: Mapped[str | None] = mapped_column(String(255))
    loan_application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_consent_principal_purpose", "data_principal_id", "purpose"),)


class DSRRequestRecord(Base):
    __tablename__ = "dsr_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_principal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    right_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), server_default="submitted")
    request_data: Mapped[dict | None] = mapped_column(JSON, server_default="{}")
    response_data: Mapped[dict | None] = mapped_column(JSON)
    workflow_id: Mapped[str | None] = mapped_column(String(100))
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DPDPAuditLog(Base):
    __tablename__ = "dpdp_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data_principal_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict | None] = mapped_column(JSON, server_default="{}")
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
