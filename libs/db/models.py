"""SQLAlchemy ORM models for the OCEN platform."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_loan_app_vendor", "vendor_gstin"),
        Index("ix_loan_app_anchor", "anchor_gstin"),
        Index("ix_loan_app_status", "status"),
        Index("ix_loan_app_idempotency", "idempotency_key", unique=True),
    )


class DecisionReceiptRecord(Base):
    __tablename__ = "decision_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    gate: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    ruleset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(String(20), default="zen-1.0")
    signature: Mapped[str | None] = mapped_column(Text)
    chain_hash: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_receipt_loan_gate", "loan_application_id", "gate"),
    )


class AnchorRecord(Base):
    __tablename__ = "anchors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    repayment_routing_active: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VendorRecord(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    udyam_number: Mapped[str | None] = mapped_column(String(30))
    udyam_category: Mapped[str | None] = mapped_column(String(10))
    onboarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
