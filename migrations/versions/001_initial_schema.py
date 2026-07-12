"""Initial schema — loan applications, decision receipts, anchors, vendors.

Revision ID: 001
Revises: None
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "anchors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), unique=True, nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("region", sa.String(100)),
        sa.Column("repayment_routing_active", sa.Boolean, default=False),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "vendors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), unique=True, nullable=False),
        sa.Column("udyam_number", sa.String(30)),
        sa.Column("udyam_category", sa.String(10)),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "loan_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_gstin", sa.String(15), nullable=False),
        sa.Column("anchor_gstin", sa.String(15), nullable=False),
        sa.Column("amount_requested", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="created"),
        sa.Column("current_gate", sa.String(50)),
        sa.Column("workflow_id", sa.String(100)),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("matched_lender_ids", JSONB),
        sa.Column("selected_lender_id", sa.String(100)),
        sa.Column("offer_data", JSONB),
        sa.Column("amount_sanctioned", sa.Numeric(14, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_loan_app_vendor", "loan_applications", ["vendor_gstin"])
    op.create_index("ix_loan_app_anchor", "loan_applications", ["anchor_gstin"])
    op.create_index("ix_loan_app_status", "loan_applications", ["status"])

    op.create_table(
        "decision_receipts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_application_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("gate", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("ruleset_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_data", JSONB),
        sa.Column("engine_version", sa.String(20), server_default="zen-1.0"),
        sa.Column("signature", sa.Text),
        sa.Column("chain_hash", sa.String(64)),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_receipt_loan_gate", "decision_receipts", ["loan_application_id", "gate"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("response_data", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("decision_receipts")
    op.drop_table("loan_applications")
    op.drop_table("vendors")
    op.drop_table("anchors")
