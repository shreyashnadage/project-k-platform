"""Add encrypted PII columns and blind indexes alongside existing plaintext.

Phase 1 of the zero-downtime encryption migration:
  002: Add new columns (this migration — additive only, no data loss)
  003: Backfill encrypted columns + drop plaintext (separate step)

Revision ID: 002
Revises: 001
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002"
down_revision: str = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Anchors: encrypted name + gstin with blind index ─────────
    op.add_column("anchors", sa.Column("name_enc", sa.LargeBinary, nullable=True))
    op.add_column("anchors", sa.Column("gstin_enc", sa.LargeBinary, nullable=True))
    op.add_column("anchors", sa.Column("gstin_idx", sa.String(64), nullable=True))

    # ── Vendors: encrypted name, gstin, udyam_number with blind indexes
    op.add_column("vendors", sa.Column("name_enc", sa.LargeBinary, nullable=True))
    op.add_column("vendors", sa.Column("gstin_enc", sa.LargeBinary, nullable=True))
    op.add_column("vendors", sa.Column("gstin_idx", sa.String(64), nullable=True))
    op.add_column("vendors", sa.Column("udyam_number_enc", sa.LargeBinary, nullable=True))
    op.add_column("vendors", sa.Column("udyam_number_idx", sa.String(64), nullable=True))

    # ── Loan Applications: encrypted vendor/anchor gstin with blind indexes
    op.add_column("loan_applications", sa.Column("vendor_gstin_enc", sa.LargeBinary, nullable=True))
    op.add_column("loan_applications", sa.Column("vendor_gstin_idx", sa.String(64), nullable=True))
    op.add_column("loan_applications", sa.Column("anchor_gstin_enc", sa.LargeBinary, nullable=True))
    op.add_column("loan_applications", sa.Column("anchor_gstin_idx", sa.String(64), nullable=True))

    # ── AA consent tracking ──────────────────────────────────────
    op.add_column("loan_applications", sa.Column("aa_consent_id", sa.String(128), nullable=True))

    # ── DPDP consent tracking ────────────────────────────────────
    op.create_table(
        "consent_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("data_principal_id", sa.String(64), nullable=False, index=True),
        sa.Column("consent_domain", sa.String(30), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("consent_text_hash", sa.String(64), nullable=False),
        sa.Column("collection_method", sa.String(30), nullable=False),
        sa.Column("aa_consent_id", sa.String(255)),
        sa.Column("loan_application_id", UUID(as_uuid=True)),
        sa.Column("metadata", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_consent_principal_purpose",
        "consent_records",
        ["data_principal_id", "purpose"],
    )

    # ── DSR requests ─────────────────────────────────────────────
    op.create_table(
        "dsr_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("data_principal_id", sa.String(64), nullable=False, index=True),
        sa.Column("right_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="submitted"),
        sa.Column("request_data", sa.JSON, server_default="{}"),
        sa.Column("response_data", sa.JSON),
        sa.Column("workflow_id", sa.String(100)),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── DPDP audit log ───────────────────────────────────────────
    op.create_table(
        "dpdp_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("data_principal_id", sa.String(64), index=True),
        sa.Column("actor_id", sa.String(100)),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", UUID(as_uuid=True)),
        sa.Column("details", sa.JSON, server_default="{}"),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("dpdp_audit_log")
    op.drop_table("dsr_requests")
    op.drop_table("consent_records")

    op.drop_column("loan_applications", "aa_consent_id")
    op.drop_column("loan_applications", "anchor_gstin_idx")
    op.drop_column("loan_applications", "anchor_gstin_enc")
    op.drop_column("loan_applications", "vendor_gstin_idx")
    op.drop_column("loan_applications", "vendor_gstin_enc")

    op.drop_column("vendors", "udyam_number_idx")
    op.drop_column("vendors", "udyam_number_enc")
    op.drop_column("vendors", "gstin_idx")
    op.drop_column("vendors", "gstin_enc")
    op.drop_column("vendors", "name_enc")

    op.drop_column("anchors", "gstin_idx")
    op.drop_column("anchors", "gstin_enc")
    op.drop_column("anchors", "name_enc")
