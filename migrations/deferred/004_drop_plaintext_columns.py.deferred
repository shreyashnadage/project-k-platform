"""Drop plaintext PII columns and rename encrypted columns.

Phase 3 of the zero-downtime encryption migration:
  002: Add _enc/_idx columns (done)
  003: Backfill encrypted data (done)
  004: Drop plaintext, rename _enc → original, rebuild indexes on _idx (THIS)

PREREQUISITES before running:
  1. Migration 003 backfill completed successfully
  2. Verification query: SELECT count(*) FROM vendors WHERE gstin_enc IS NULL → 0
  3. Application code updated to read from _enc columns (dual-read phase complete)
  4. No in-flight workflows referencing plaintext columns

Revision ID: 004
Revises: 003
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Anchors ──────────────────────────────────────────────────
    op.drop_column("anchors", "name")
    op.drop_column("anchors", "gstin")
    op.alter_column("anchors", "name_enc", new_column_name="name_encrypted", nullable=False)
    op.alter_column("anchors", "gstin_enc", new_column_name="gstin_encrypted", nullable=False)
    op.alter_column("anchors", "gstin_idx", nullable=False)
    op.create_index("ix_anchor_gstin_idx", "anchors", ["gstin_idx"], unique=True)

    # ── Vendors ──────────────────────────────────────────────────
    op.drop_column("vendors", "name")
    op.drop_column("vendors", "gstin")
    op.drop_column("vendors", "udyam_number")
    op.alter_column("vendors", "name_enc", new_column_name="name_encrypted", nullable=False)
    op.alter_column("vendors", "gstin_enc", new_column_name="gstin_encrypted", nullable=False)
    op.alter_column("vendors", "gstin_idx", nullable=False)
    op.alter_column("vendors", "udyam_number_enc", new_column_name="udyam_encrypted")
    op.alter_column("vendors", "udyam_number_idx", new_column_name="udyam_idx")
    op.create_index("ix_vendor_gstin_idx", "vendors", ["gstin_idx"], unique=True)
    op.create_index("ix_vendor_udyam_idx", "vendors", ["udyam_idx"])

    # ── Loan Applications ────────────────────────────────────────
    op.drop_index("ix_loan_app_vendor")
    op.drop_index("ix_loan_app_anchor")
    op.drop_column("loan_applications", "vendor_gstin")
    op.drop_column("loan_applications", "anchor_gstin")
    op.alter_column(
        "loan_applications", "vendor_gstin_enc",
        new_column_name="vendor_gstin_encrypted", nullable=False,
    )
    op.alter_column(
        "loan_applications", "anchor_gstin_enc",
        new_column_name="anchor_gstin_encrypted", nullable=False,
    )
    op.alter_column("loan_applications", "vendor_gstin_idx", nullable=False)
    op.alter_column("loan_applications", "anchor_gstin_idx", nullable=False)
    op.create_index("ix_loan_app_vendor_idx", "loan_applications", ["vendor_gstin_idx"])
    op.create_index("ix_loan_app_anchor_idx", "loan_applications", ["anchor_gstin_idx"])


def downgrade() -> None:
    # ── Loan Applications (restore plaintext) ────────────────────
    op.drop_index("ix_loan_app_anchor_idx")
    op.drop_index("ix_loan_app_vendor_idx")
    op.alter_column("loan_applications", "anchor_gstin_idx", nullable=True)
    op.alter_column("loan_applications", "vendor_gstin_idx", nullable=True)
    op.alter_column(
        "loan_applications", "anchor_gstin_encrypted",
        new_column_name="anchor_gstin_enc",
    )
    op.alter_column(
        "loan_applications", "vendor_gstin_encrypted",
        new_column_name="vendor_gstin_enc",
    )
    op.add_column("loan_applications", sa.Column("anchor_gstin", sa.String(15), nullable=True))
    op.add_column("loan_applications", sa.Column("vendor_gstin", sa.String(15), nullable=True))
    op.create_index("ix_loan_app_anchor", "loan_applications", ["anchor_gstin"])
    op.create_index("ix_loan_app_vendor", "loan_applications", ["vendor_gstin"])

    # ── Vendors (restore plaintext) ──────────────────────────────
    op.drop_index("ix_vendor_udyam_idx")
    op.drop_index("ix_vendor_gstin_idx")
    op.alter_column("vendors", "udyam_idx", new_column_name="udyam_number_idx")
    op.alter_column("vendors", "udyam_encrypted", new_column_name="udyam_number_enc")
    op.alter_column("vendors", "gstin_idx", nullable=True)
    op.alter_column("vendors", "gstin_encrypted", new_column_name="gstin_enc")
    op.alter_column("vendors", "name_encrypted", new_column_name="name_enc")
    op.add_column("vendors", sa.Column("udyam_number", sa.String(30), nullable=True))
    op.add_column("vendors", sa.Column("gstin", sa.String(15), nullable=True, unique=True))
    op.add_column("vendors", sa.Column("name", sa.String(255), nullable=True))

    # ── Anchors (restore plaintext) ──────────────────────────────
    op.drop_index("ix_anchor_gstin_idx")
    op.alter_column("anchors", "gstin_idx", nullable=True)
    op.alter_column("anchors", "gstin_encrypted", new_column_name="gstin_enc")
    op.alter_column("anchors", "name_encrypted", new_column_name="name_enc")
    op.add_column("anchors", sa.Column("gstin", sa.String(15), nullable=True, unique=True))
    op.add_column("anchors", sa.Column("name", sa.String(255), nullable=True))
