"""Add vendor invite tracking columns (invite_token, status, invited_by, phone).

Enables real persistence for the ops vendor invite/activate flow
(services/borrower_gateway/ops_api.py), which previously never wrote to
the vendors table at all.

Branches off "005", not "004" — deliberately. Migration 005 (RLS) was
re-parented off 003 to unblock it from 004 (the zero-downtime PII
encryption cutover, which is not runnable against the current codebase —
see 005's docstring for the full explanation and migrations/deferred/
for where 004 now lives). This migration chains after 005 so the active
revision graph is a single line: 001 → 002 → 003 → 005 → 006, with no
ambiguous heads.

Revision ID: 006
Revises: 005
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("phone", sa.String(13), nullable=True))
    op.add_column("vendors", sa.Column("phone_enc", sa.LargeBinary(), nullable=True))
    op.add_column("vendors", sa.Column("phone_idx", sa.String(64), nullable=True))
    op.add_column("vendors", sa.Column("invite_token", sa.String(64), nullable=True))
    op.add_column(
        "vendors",
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("vendors", sa.Column("invited_by", sa.String(255), nullable=True))

    op.create_index("ix_vendor_invite_token", "vendors", ["invite_token"], unique=True)
    op.create_index("ix_vendor_phone_idx", "vendors", ["phone_idx"])


def downgrade() -> None:
    op.drop_index("ix_vendor_phone_idx", table_name="vendors")
    op.drop_index("ix_vendor_invite_token", table_name="vendors")

    op.drop_column("vendors", "invited_by")
    op.drop_column("vendors", "status")
    op.drop_column("vendors", "invite_token")
    op.drop_column("vendors", "phone_idx")
    op.drop_column("vendors", "phone_enc")
    op.drop_column("vendors", "phone")
