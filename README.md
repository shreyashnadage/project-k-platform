# OCEN Platform — Anchor-Led Vendor Receivables Financing

A Loan Agent (LA) and Derived Data Provider (DDP) on India's OCEN 4.0 framework.

## Quickstart

```bash
# Prerequisites: Docker, Python 3.12+, uv (https://docs.astral.sh/uv/)

# 1. Install Python dependencies
make init

# 2. Start local infrastructure (Postgres, Redpanda, Temporal, Keycloak)
make up

# 3. Create Redpanda topics
make topics

# 4. Run tests
make test

# 5. See all available commands
make help
```

## Architecture

See [CLAUDE.md](./CLAUDE.md) for full architecture context, coding conventions, and domain terminology.

See [docs/adr/](./docs/adr/) for Architecture Decision Records.

## Project Structure

- `libs/` — Shared Python libraries (models, events, audit, engine wrappers)
- `services/` — Independent services (LA orchestrator, Trust Graph, DDP, borrower gateway)
- `rules/` — GoRules JDM decision tables (git-versioned, content-addressed)
- `schemas/` — Frozen event schemas
- `infra/` — Docker, Kubernetes, Terraform configs
- `docs/` — ADRs, guides, architecture diagrams
- `tests/` — Unit and integration tests

## Phased Build

| Phase | What | Key Deliverable |
|-------|------|-----------------|
| 0 | Foundation | Infra, event backbone, audit layer, CI |
| 1 | VDP Wedge | ERPNext custom app for anchor onboarding |
| 2 | Trust Graph | dbt models, derived attributes, AGE graph |
| 3 | LA on OCEN | Temporal workflows, Zen rules, AA, borrower PWA |
| 4 | DDP | Verifiable credentials, Superset dashboards |
| 5 | Company | Formal registration |

See [docs/guides/PHASE-0-TASKS.md](./docs/guides/PHASE-0-TASKS.md) for detailed Phase 0 tasks.
