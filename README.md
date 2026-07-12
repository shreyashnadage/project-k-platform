# OCEN Platform — Anchor-Led Vendor Receivables Financing

A Loan Agent (LA) and Derived Data Provider (DDP) on India's OCEN 4.0 framework, enabling deep-tier MSME vendors of mid-market manufacturing corporates to access working capital financing backed by confirmed receivables.

## What It Does

1. **Vendor applies** for a loan against an invoice from their anchor (buyer)
2. **Platform validates** the invoice (Kind 1 attestation: valid IRN + GST IMS acceptance + repayment routing)
3. **Decision gates D0-D3** evaluate eligibility, data sufficiency, derived attributes, and lender pre-screening
4. **OCEN network submission** sends the application to matched lenders with signed payloads (JWS RFC 7797)
5. **Lender responds asynchronously** with offers, which are routed back to the borrower
6. **Trust Graph** accumulates attestation + origination + repayment data as a proprietary moat

## Quickstart

```bash
# Prerequisites: Python 3.12+, uv (https://docs.astral.sh/uv/)

# 1. Install Python dependencies
uv sync

# 2. Start local infrastructure (Postgres, Redpanda, Temporal, Keycloak)
make up

# 3. Run tests (71 tests, all mocked — no external dependencies needed)
make test

# 4. Start the Temporal worker
make worker

# 5. Start the Borrower Gateway API
make gateway
```

## Architecture

```
Borrower (MSME Vendor)
    │
    ▼
[Borrower Gateway] ← FastAPI, OCEN callback endpoints
    │
    ▼
[Temporal Workflow] ← Loan origination saga (D0→AA→D1→D2→D3→Submit)
    │
    ├── [Zen Engine] ← Decision rules (D0-D3)
    ├── [AA Client] ← Account Aggregator data fetch
    ├── [OCEN Network Client] ← Submit to lenders (JWS signed, OAuth2)
    │       ├── Token Service (client_credentials)
    │       ├── JWS Signer (RFC 7797 detached signatures)
    │       ├── Registry Client (participant discovery)
    │       └── Heartbeat Service (analytics events)
    └── [Trust Graph] ← Proprietary scoring (dbt + PostgreSQL + AGE)
```

See [CLAUDE.md](./CLAUDE.md) for full architecture principles, IP boundary rules, and domain terminology.

## Project Structure

```
libs/
├── ocen_client/         # OCEN 4.0 network protocol implementation
│   ├── auth/            # OAuth2 token service + config
│   ├── jws/             # JWS detached signature (RFC 7797, RSA-SHA256)
│   ├── models/          # OCEN data models (MetaData, LoanApplication, etc.)
│   ├── registry.py      # Participant & product network discovery
│   ├── heartbeat.py     # Analytics event emission
│   └── network_client.py # Top-level orchestrator
├── integrations/        # Protocol definitions + factory (mock/real toggle)
├── mocks/               # Mock clients for AA, OCEN, GST, Lender
├── zen_rules/           # GoRules Zen decision engine wrapper
├── audit/               # Signed decision receipts
└── common/              # Logging, middleware, events, models

services/
├── borrower_gateway/    # FastAPI — borrower API + OCEN callback endpoints
├── la_orchestrator/     # Temporal workflow + activities
├── vdp_wedge/           # Invoice ingestion + Kind 1 attestation
├── ddp_engine/          # Derived Data Provider
└── trust_graph/         # Trust scoring engine

rules/                   # GoRules JDM decision tables (git-versioned)
schemas/                 # Frozen event schemas (Redpanda)
tests/                   # 71 tests (unit + integration + e2e)
```

## OCEN Network Integration

The platform implements the full OCEN 4.0 network transaction protocol:

| Step | What Happens | Component |
|------|-------------|-----------|
| Auth | Get OAuth2 bearer token via client_credentials | `libs/ocen_client/auth/` |
| Sign | Sign request body with RSA-SHA256 (RFC 7797 detached JWS) | `libs/ocen_client/jws/` |
| Discover | Query OCEN Registry for lenders in product network | `libs/ocen_client/registry.py` |
| Submit | POST to lender's createLoanRequest with Bearer + x-jws-signature | `libs/ocen_client/network_client.py` |
| ACK | Lender returns immediate OcenAckResponse | — |
| Response | Lender async POSTs back to our callback endpoints | `services/borrower_gateway/app.py` |
| Signal | Callback signals the waiting Temporal workflow | Temporal signal |
| Heartbeat | Every step emits analytics events | `libs/ocen_client/heartbeat.py` |

### Callback Endpoints (Lender → LA)

All at `/v4.0.0alpha/loanApplications/`:
- `createLoanResponse` — loan application decision
- `generateOffersResponse` — generated offers
- `setOffersResponse` — offer selection confirmation
- `loanAgreementResponse` — loan agreement for e-sign
- `grantLoanResponse` — loan grant confirmation
- `triggerDisbursementResponse` — disbursement confirmation
- `triggerRepaymentResponse` — repayment events
- `setRepaymentPlanResponse` — repayment plan

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `OCEN_USE_MOCKS` | `true` (default) uses mock clients, `false` hits real APIs |
| `OCEN_CLIENT_ID` | OAuth2 client ID for OCEN network |
| `OCEN_CLIENT_SECRET` | OAuth2 client secret |
| `OCEN_PARTICIPANT_ID` | Your participant role ID on OCEN |
| `OCEN_ORG_ID` | Your organization ID |
| `OCEN_PRODUCT_ID` | Product ID |
| `OCEN_PRODUCT_NETWORK_ID` | Product network ID |
| `TEMPORAL_ADDRESS` | Temporal server (default: localhost:7233) |

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run just OCEN client tests
uv run pytest tests/test_ocen_client/ -v

# Run with coverage
uv run pytest tests/ --cov=libs --cov=services
```

## Phased Build

| Phase | What | Status |
|-------|------|--------|
| 0 | Foundation (infra, events, audit, CI) | Done |
| 1 | VDP Wedge (ERPNext, Kind 1 attestation) | Done |
| 2 | Trust Graph (dbt, derived attributes) | Done |
| 3 | LA on OCEN (Temporal, Zen rules, AA, OCEN network protocol) | Done |
| 4 | DDP (Verifiable credentials, dashboards) | Planned |
| 5 | Company (Formal registration) | Planned |

## Documentation

- [CLAUDE.md](./CLAUDE.md) — Architecture principles, tech stack, domain terms
- [docs/guides/PHASE-0-TASKS.md](./docs/guides/PHASE-0-TASKS.md) — Phase 0 tasks
- [docs/userguide.md](./docs/userguide.md) — Plain-English user guide
- [docs/adr/](./docs/adr/) — Architecture Decision Records
