"""Enable PostgreSQL Row-Level Security for tenant isolation.

Reads its policy shape from tenancy.yaml (checked into the repo root) so
the SQL here and the config the application reads stay in lockstep — this
migration is a direct application of tenancy.yaml's templates, not an
independent design.

Tables scoped: loan_applications (direct anchor_gstin column),
decision_receipts (via a join back to loan_applications, since it only
carries loan_application_id — see tenancy.yaml's joined_scoped_tables).

Bypass roles (platform-admin, operations) are not implemented as Postgres
roles here — the application sets a sentinel session value
("__RLS_BYPASS__", see libs/db/rls.py::clear_tenant_context) that every
policy explicitly checks for, rather than relying on a Postgres BYPASSRLS
grant. This keeps bypass-vs-scoped entirely inside the tenancy.yaml /
rls.py logic instead of splitting it across DB role management too.

PREREQUISITES before running in any environment with live traffic:
  1. Every code path that queries loan_applications or decision_receipts
     must go through libs.db.rls.tenant_scoped_session() (or an equivalent
     dependency that calls set_tenant_context/clear_tenant_context) —
     otherwise every query silently returns zero rows, since RLS is
     enabled at the table level regardless of whether the application's
     RBAC middleware happens to be turned on for a given deployment.
  2. As of this migration, no endpoint has been wired to
     tenant_scoped_session() yet (Phase 2 of the RBAC/role-UIs plan ships
     the mechanism; wiring individual endpoints is a follow-up). Do not
     run this migration against a database any running service still
     queries via the plain libs.db.engine.get_session() dependency for
     these two tables, or those endpoints will start returning empty
     results.

Revision ID: 005
Revises: 004
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | None = None
depends_on: str | None = None

_SESSION_VAR = "app.tenant_id"
_BYPASS_SENTINEL = "__RLS_BYPASS__"


def upgrade() -> None:
    # loan_applications — direct tenant column.
    op.execute("ALTER TABLE loan_applications ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY anchor_isolation_loans ON loan_applications
          FOR ALL
          USING (
            current_setting('{_SESSION_VAR}', true) = '{_BYPASS_SENTINEL}'
            OR anchor_gstin = current_setting('{_SESSION_VAR}', true)
          )
          WITH CHECK (
            current_setting('{_SESSION_VAR}', true) = '{_BYPASS_SENTINEL}'
            OR anchor_gstin = current_setting('{_SESSION_VAR}', true)
          )
        """
    )

    # decision_receipts — scoped via join to loan_applications.
    op.execute("ALTER TABLE decision_receipts ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY anchor_isolation_receipts ON decision_receipts
          FOR ALL
          USING (
            current_setting('{_SESSION_VAR}', true) = '{_BYPASS_SENTINEL}'
            OR loan_application_id IN (
              SELECT id FROM loan_applications
              WHERE anchor_gstin = current_setting('{_SESSION_VAR}', true)
            )
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS anchor_isolation_receipts ON decision_receipts")
    op.execute("ALTER TABLE decision_receipts DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS anchor_isolation_loans ON loan_applications")
    op.execute("ALTER TABLE loan_applications DISABLE ROW LEVEL SECURITY")
