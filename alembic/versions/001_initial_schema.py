"""Initial schema from init-db.sql

Revision ID: 001
Revises: None
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    op.execute("""
        CREATE TABLE platform.anchors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            gstin TEXT NOT NULL UNIQUE,
            onboarded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE platform.vendors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            gstin TEXT NOT NULL UNIQUE,
            onboarded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE platform.anchor_vendors (
            anchor_id UUID REFERENCES platform.anchors(id),
            vendor_id UUID REFERENCES platform.vendors(id),
            relationship_type TEXT NOT NULL DEFAULT 'buyer-supplier',
            established_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (anchor_id, vendor_id)
        )
    """)

    op.execute("""
        CREATE TABLE platform.invoices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            irn TEXT UNIQUE,
            anchor_id UUID REFERENCES platform.anchors(id),
            vendor_id UUID REFERENCES platform.vendors(id),
            amount NUMERIC(15,2) NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            issue_date DATE NOT NULL,
            due_date DATE NOT NULL,
            ims_status TEXT NOT NULL DEFAULT 'pending',
            irn_valid BOOLEAN NOT NULL DEFAULT false,
            repayment_routing_active BOOLEAN NOT NULL DEFAULT false,
            kind1_attested BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE platform.loan_applications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            invoice_id UUID REFERENCES platform.invoices(id),
            vendor_id UUID REFERENCES platform.vendors(id),
            anchor_id UUID REFERENCES platform.anchors(id),
            status TEXT NOT NULL DEFAULT 'initiated',
            current_gate TEXT,
            amount_requested NUMERIC(15,2),
            amount_sanctioned NUMERIC(15,2),
            lender_id TEXT,
            workflow_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE platform.lender_filters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lender_id TEXT NOT NULL,
            lender_name TEXT NOT NULL,
            min_amount NUMERIC(15,2) DEFAULT 0,
            max_amount NUMERIC(15,2) DEFAULT 99999999.99,
            accepted_sectors TEXT[] DEFAULT '{}',
            min_vintage_months INT DEFAULT 0,
            max_dso_days INT DEFAULT 90,
            active BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE audit.decision_receipts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_application_id UUID NOT NULL,
            gate TEXT NOT NULL,
            ruleset_hash TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            output_hash TEXT NOT NULL,
            outcome TEXT NOT NULL,
            chain_hash TEXT NOT NULL,
            previous_chain_hash TEXT,
            signature TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            receipt_payload JSONB NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE platform.event_outbox (
            id BIGSERIAL PRIMARY KEY,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            published_at TIMESTAMPTZ,
            published BOOLEAN NOT NULL DEFAULT false
        )
    """)

    op.execute("""
        CREATE INDEX idx_outbox_unpublished
        ON platform.event_outbox (created_at)
        WHERE published = false
    """)

    op.execute("""
        CREATE INDEX idx_invoices_anchor ON platform.invoices(anchor_id)
    """)
    op.execute("""
        CREATE INDEX idx_invoices_vendor ON platform.invoices(vendor_id)
    """)
    op.execute("""
        CREATE INDEX idx_loan_apps_status ON platform.loan_applications(status)
    """)
    op.execute("""
        CREATE INDEX idx_receipts_loan ON audit.decision_receipts(loan_application_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform.event_outbox CASCADE")
    op.execute("DROP TABLE IF EXISTS audit.decision_receipts CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.lender_filters CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.loan_applications CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.invoices CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.anchor_vendors CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.vendors CASCADE")
    op.execute("DROP TABLE IF EXISTS platform.anchors CASCADE")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE")
