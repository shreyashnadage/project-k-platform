"""Add vendor invite tracking columns (invite_token, status, invited_by, phone).

Enables real persistence for the ops vendor invite/activate flow
(services/borrower_gateway/ops_api.py), which previously never wrote to
the vendors table at all.

Branches off "003", not "005" — deliberately. Migrations 004/005 (the
zero-downtime PII encryption cutover) rename/drop the plaintext gstin/name
columns this migration and the rest of the DPDP rights/retention code
(libs/db/data_source.py, libs/db/retention_handlers.py) still directly
query and assign — applying 004 today would break both of those, and 005's
RLS policies still reference the pre-004 plaintext `anchor_gstin` column
name on loan_applications, so 004→005 as currently written don't even
chain correctly. Until that's resolved in a dedicated pass, this migration
targets the last internally-consistent schema state (003) that the rest
of the codebase already assumes.

Revision ID: 006
Revises: 003
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str = "003"
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
