# CLAUDE.md — OCEN Platform (Anchor-Led Vendor Receivables Financing)

## What This Project Is

A Loan Agent (LA) and Derived Data Provider (DDP) on India's OCEN 4.0 framework, enabling anchor-led vendor-side receivables financing for deep-tier MSME vendors of mid-market auto-ancillary and manufacturing corporates in western Maharashtra.

**The core insight:** Lenders care about "Kind 1 attestation" — a confirmed receivable (validated invoice with IRN + GST IMS acceptance) PLUS repayment routing through the anchor's payable — NOT credit scores. The moat is a proprietary "Trust Graph" that is the only system seeing anchor attestation + loan origination + repayment outcome together.

## Architecture Principles (NEVER violate these)

1. **IP Boundary:** GPL/AGPL systems-of-record (ERPNext, Fineract) sit BELOW the IP boundary. The proprietary Trust Graph sits ABOVE. They communicate ONLY via REST APIs and the Redpanda event bus. Never link code across this boundary.
2. **Decision ≠ Orchestration:** Temporal owns durable control flow (sagas, retries, timers). GoRules Zen Engine owns stateless point-evaluations. Rules are ALWAYS called from Temporal activities, NEVER from workflow code (determinism).
3. **Never encode the lender's credit policy.** D0–D3 are ours (eligibility, data sufficiency, derived attributes, pre-screen). D4 (underwriting) is the lender's — regulatory and commercial boundary.
4. **Repayment goes anchor → lender directly.** No pool/pass-through account controlled by us. RBI Digital Lending Directions 2025 prohibit it.
5. **Event sourcing for trade events.** The Redpanda stream is the append-only source of truth for attestation, origination, and repayment events. Schema is frozen and versioned.
6. **Content-addressed, signed decision receipts.** Every rule evaluation produces a receipt {input_hash, ruleset_hash, output, timestamp, engine_version}, signed with KMS, written to the event stream. This is the DDP audit trail.

## Tech Stack

| Layer | Component | Language | Licence | Notes |
|-------|-----------|----------|---------|-------|
| Infra | RKE2/K8s, APISIX, SigNoz | — | Apache-2.0 | AWS ap-south-1 |
| Event bus | Redpanda | — | BSL/Community | Kafka-API compatible, no JVM |
| Database | PostgreSQL 16+ | — | PostgreSQL | Primary store + Apache AGE for graph |
| Internal IAM | Keycloak | Java | Apache-2.0 | Workforce/admin users |
| Borrower CIAM | Ory Kratos + Hydra | Go | Apache-2.0 | API-first, headless, PWA-friendly |
| VDP wedge | ERPNext/Frappe | Python | GPLv3 | BELOW IP boundary |
| Lending core | Apache Fineract | Java | Apache-2.0 | BELOW IP boundary, REST + events |
| Trust Graph | dbt + PostgreSQL + AGE | Python/SQL | Proprietary | ABOVE IP boundary — THE MOAT |
| Orchestration | Temporal | — | MIT | Python SDK for workers |
| Decision engine | GoRules Zen | Rust/Python | MIT | In-process via Python bindings |
| AA gateway | Setu / Perfios | — | Commercial | Model 2 under partner NBFC's FIU |
| VC issuance | Sunbird RC | Java | MIT | W3C Verifiable Credentials |
| BI | Superset + Metabase | Python/Java | Apache-2.0/AGPL | Lender dashboards |
| Borrower UX | React/Next.js PWA | TypeScript | Proprietary | Vernacular-first |

## Coding Conventions

- **Language:** Python 3.12+ preferred. Use `uv` for package management.
- **Type hints:** Always. Use `from __future__ import annotations`. Pydantic v2 for data models.
- **Async:** Use `asyncio` for I/O-bound services. Temporal workers use the Temporal Python SDK's async activity pattern.
- **Testing:** pytest. Minimum: unit tests for decision rules, integration tests for Temporal workflows (use Temporal's test server), contract tests for API boundaries.
- **Formatting:** ruff (linting + formatting). Config in pyproject.toml.
- **Error handling:** Never swallow exceptions. Use structured error types. Temporal activities must be idempotent.
- **Secrets:** Never in code. Use environment variables locally, AWS Secrets Manager + External Secrets Operator in production.
- **Logging:** structlog (JSON). Include correlation IDs (trace_id, workflow_id, loan_application_id).
- **Event schemas:** All events in `schemas/` with version numbers. Backward-compatible evolution only. Breaking changes = new event type.

## Key Domain Terms

- **Kind 1 attestation:** Valid IRN + active GST IMS "Accept" by anchor + repayment routing active
- **Trust Graph:** Proprietary data layer seeing attestation + origination + repayment outcome
- **D0–D3:** Our decision gates (Kind 1 gate, AA data sufficiency, derived attributes, lender pre-screen)
- **D4:** Lender's underwriting — NOT ours
- **IP boundary:** Network boundary (REST + event bus) separating GPL code from proprietary code
- **Trade event:** Immutable fact in the event stream (InvoiceAttested, LoanOriginated, RepaymentObserved, etc.)
- **Decision receipt:** Signed, content-addressed record of a rule evaluation
- **Anchor:** The large buyer (auto-ancillary / manufacturing corporate)
- **Vendor/Borrower:** The MSME supplier who gets the loan
- **IRN:** Invoice Reference Number — 64-char SHA-256 hash from GST e-invoicing portal
- **IMS:** Invoice Management System on GST portal (Accept/Reject/Pending)

## Decision Gates (Rule Evaluation Flow)

```
Loan Request
  │
  ▼
[D0] Kind 1 Gate (Zen, activity)
  │ GSTIN valid? IRN valid? IMS accepted? Routing active?
  │ FAIL → reject, lender never sees it
  ▼
[AA Fetch] Consent + data pull (Temporal activity, async callback)
  │
  ▼
[D1] Data Sufficiency Gate (Zen, activity)
  │ Enough months? Fresh enough? GST filed?
  ▼
[D2] Derived Attributes + Flags (Zen, activity) — DDP function
  │ DSO/DPO/CCC, concentration, dilution, anchor payment history
  │ Output: derived-data package + risk flags
  │ Stamp: ruleset_hash + signed receipt → event stream
  ▼
[D3] Lender Pre-screen (Zen, activity)
  │ Match against each lender's published filters
  │ Output: ranked eligible lenders
  ▼
[OCEN Submit] → Lender's D4 (their underwriting, not ours)
  ▼
[Offer] → [Acceptance + e-sign] → [Disbursement] → [Repayment tracking]
```

## Running Locally

```bash
# Start infrastructure
make up

# Run tests
make test

# Lint + format
make lint

# Start Temporal worker (la-orchestrator)
make worker

# Run dbt models (trust-graph)
make dbt-run
```

## What NOT to Build

- ML credit scoring engine (the moat is structural, not predictive)
- Independent AA/FIU infrastructure (use Setu/Perfios under partner NBFC)
- Blockchain anything (signed hash chain in Postgres/Redpanda suffices)
- Social media scoring (noise for Kolhapur-belt MSMEs)
- Lender's underwriting logic (D4 is theirs, not ours)
