-- Database initialization for OCEN Platform
-- Run automatically by Postgres container on first start

-- Separate schemas for clean boundaries
CREATE SCHEMA IF NOT EXISTS platform;     -- Core platform tables
CREATE SCHEMA IF NOT EXISTS trust_graph;  -- Trust Graph (proprietary, above IP boundary)
CREATE SCHEMA IF NOT EXISTS audit;        -- Decision receipts, hash chain
CREATE SCHEMA IF NOT EXISTS keycloak;     -- Keycloak internal IAM (managed by Keycloak)

-- ─── Platform Schema ───────────────────────────────────────

-- Anchors (large buyers / corporates)
CREATE TABLE platform.anchors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    gstin CHAR(15) NOT NULL UNIQUE,
    sector TEXT,
    region TEXT,
    repayment_routing_active BOOLEAN DEFAULT FALSE,
    onboarded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vendors (MSME suppliers / borrowers)
CREATE TABLE platform.vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    gstin CHAR(15) NOT NULL UNIQUE,
    udyam_number TEXT,
    udyam_category TEXT CHECK (udyam_category IN ('micro', 'small', 'medium')),
    onboarded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Anchor-Vendor relationships
CREATE TABLE platform.anchor_vendors (
    anchor_id UUID NOT NULL REFERENCES platform.anchors(id),
    vendor_id UUID NOT NULL REFERENCES platform.vendors(id),
    validated_at TIMESTAMPTZ,
    PRIMARY KEY (anchor_id, vendor_id)
);

-- Invoices with e-invoicing and IMS status
CREATE TABLE platform.invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    irn CHAR(64) NOT NULL UNIQUE,
    anchor_gstin CHAR(15) NOT NULL,
    vendor_gstin CHAR(15) NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) DEFAULT 'INR',
    ims_status TEXT DEFAULT 'pending' CHECK (ims_status IN ('accepted', 'rejected', 'pending', 'deemed_accepted')),
    ims_checked_at TIMESTAMPTZ,
    irn_validated BOOLEAN DEFAULT FALSE,
    irn_validated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Loan Applications
CREATE TABLE platform.loan_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES platform.vendors(id),
    anchor_id UUID NOT NULL REFERENCES platform.anchors(id),
    invoice_id UUID NOT NULL REFERENCES platform.invoices(id),
    requested_amount NUMERIC(15,2) NOT NULL,
    requested_tenor_days INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    kind1_attested BOOLEAN DEFAULT FALSE,
    kind1_attested_at TIMESTAMPTZ,
    selected_lender_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lender filters (D3 pre-screen — ONLY published coarse filters)
CREATE TABLE platform.lender_filters (
    lender_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lender_name TEXT NOT NULL,
    min_ticket NUMERIC(15,2) DEFAULT 50000,
    max_ticket NUMERIC(15,2) DEFAULT 5000000,
    accepted_sectors TEXT[] DEFAULT '{}',
    accepted_regions TEXT[] DEFAULT '{}',
    max_tenor_days INT DEFAULT 180,
    min_udyam_category TEXT DEFAULT 'micro',
    max_anchor_concentration_pct NUMERIC(5,2) DEFAULT 100,
    requires_gst_filed_last_6m INT DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Audit Schema ───────────────────────────────���──────────

-- Decision receipts (signed, content-addressed)
CREATE TABLE audit.decision_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_application_id UUID NOT NULL,
    gate TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('pass', 'fail', 'flag')),
    ruleset_hash CHAR(64) NOT NULL,
    input_hash CHAR(64) NOT NULL,
    output JSONB NOT NULL DEFAULT '{}',
    engine_version TEXT NOT NULL,
    signature TEXT,
    chain_hash CHAR(64),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Index for chain verification (ordered sequence per application)
    CONSTRAINT unique_gate_per_app UNIQUE (loan_application_id, gate)
);

CREATE INDEX idx_receipts_app_id ON audit.decision_receipts(loan_application_id);
CREATE INDEX idx_receipts_evaluated ON audit.decision_receipts(evaluated_at);

-- ─── Transactional Outbox ──────────────────────────────────
-- Events are written here in the same transaction as the domain change,
-- then relayed to Redpanda by a separate process.

CREATE TABLE platform.event_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT 'ocen.trade-events.v1',
    key TEXT NOT NULL,
    payload JSONB NOT NULL,
    published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished ON platform.event_outbox(published, created_at)
    WHERE NOT published;

-- ─── Updated-at Trigger ────────────────────────────────────

CREATE OR REPLACE FUNCTION platform.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_anchors_updated
    BEFORE UPDATE ON platform.anchors
    FOR EACH ROW EXECUTE FUNCTION platform.set_updated_at();

CREATE TRIGGER trg_vendors_updated
    BEFORE UPDATE ON platform.vendors
    FOR EACH ROW EXECUTE FUNCTION platform.set_updated_at();

CREATE TRIGGER trg_loan_apps_updated
    BEFORE UPDATE ON platform.loan_applications
    FOR EACH ROW EXECUTE FUNCTION platform.set_updated_at();
