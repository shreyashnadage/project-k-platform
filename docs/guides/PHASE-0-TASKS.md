# Phase 0 — Foundation Tasks

These are ordered by dependency. Each task is scoped for a single Claude Code session.

## Task 0.1: Local Dev Stack Smoke Test
**Goal:** `make up` brings up all infrastructure and everything is reachable.
**Steps:**
1. Run `docker compose up -d`
2. Verify Postgres (port 5432) accepts connections and `init-db.sql` ran
3. Verify Postgres-AGE (port 5433) has the `ag_catalog` extension
4. Verify Redpanda (port 19092) is reachable; run `scripts/create-topics.sh`
5. Verify Temporal (port 7233) is reachable; check Temporal UI at :8233
6. Verify Keycloak (port 8080) has the `ocen-platform` realm imported
**Done when:** All services healthy, topics exist, Keycloak realm visible.

## Task 0.2: Python Environment Bootstrap
**Goal:** `uv sync` installs all deps; `make lint` and `make test` pass on empty tests.
**Steps:**
1. Install uv if not present
2. Run `uv sync --all-extras`
3. Create a minimal `tests/test_smoke.py` that imports `libs.common.models`
4. Run `make lint` — fix any ruff issues
5. Run `make test` — green
**Done when:** CI-ready Python environment with passing smoke test.

## Task 0.3: Event Schema Registration
**Goal:** Frozen event schemas registered with Redpanda Schema Registry.
**Steps:**
1. Create JSON Schema files in `schemas/` for `TradeEvent` envelope and key payload types
2. Write `scripts/register-schemas.sh` to register them with Schema Registry at :18081
3. Validate a sample event against the schema programmatically
**Done when:** Schemas registered, validation working.

## Task 0.4: Event Producer Integration Test
**Goal:** Produce and consume a `TradeEvent` on Redpanda end-to-end.
**Steps:**
1. Write `tests/test_event_producer.py` (integration test, requires `make up`)
2. Produce an `ANCHOR_ONBOARDED` event via `EventProducer`
3. Consume it back and verify deserialization
**Done when:** Round-trip event test passes.

## Task 0.5: Audit Receipt Unit Tests
**Goal:** `ReceiptSigner` and `ChainVerifier` are tested.
**Steps:**
1. Write `tests/test_audit_receipts.py`
2. Test: create receipt → verify signature
3. Test: create chain of 5 receipts → verify chain integrity
4. Test: tamper with one receipt → chain verification fails
**Done when:** All receipt tests pass.

## Task 0.6: Zen Engine Integration
**Goal:** Load and evaluate the D0 Kind 1 gate ruleset.
**Steps:**
1. Write `tests/test_zen_engine.py`
2. Load `rules/d0-kind1-gate.json` via `ZenDecisionEngine`
3. Test: all conditions met → outcome=pass
4. Test: IMS deemed_accepted → outcome=flag
5. Test: IMS rejected → outcome=fail
6. Verify `ruleset_hash` is deterministic
**Done when:** D0 gate evaluates correctly with content-addressed hashes.

## Task 0.7: Temporal Workflow Skeleton Test
**Goal:** `LoanOriginationWorkflow` runs end-to-end with stub activities.
**Steps:**
1. Write `tests/test_workflow.py` using Temporal's test environment
2. Run workflow with a mock loan application ID
3. Verify it calls D0 → AA → D1 → D2 → D3 → submit in order
4. Test: D0 fail → workflow returns rejected at D0
5. Test: D3 no lenders → workflow returns rejected at D3
**Done when:** Workflow skeleton passes with stubs.

## Task 0.8: Alembic Migration Setup
**Goal:** Database migrations managed by Alembic, not raw SQL.
**Steps:**
1. Initialize Alembic in the project root
2. Create initial migration from `scripts/init-db.sql` schema
3. Verify `alembic upgrade head` on a fresh database matches the init script
4. Update `make` targets for `make migrate` and `make migrate-down`
**Done when:** Migrations are the canonical schema source.

## Task 0.9: Structlog + Correlation ID Middleware
**Goal:** JSON structured logging with trace/correlation IDs across all services.
**Steps:**
1. Create `libs/common/logging.py` — structlog configuration
2. Add correlation-ID middleware for FastAPI (extract from header or generate)
3. Wire into Temporal activity context (workflow_id, run_id)
**Done when:** All log entries are JSON with correlation IDs.

## Task 0.10: CI Pipeline Skeleton
**Goal:** GitHub Actions / GitLab CI runs lint + unit tests on every push.
**Steps:**
1. Create `.github/workflows/ci.yml` (or `.gitlab-ci.yml`)
2. Steps: checkout, install uv, sync deps, ruff check, mypy, pytest (unit only)
3. Integration tests run only on `main` branch merges
**Done when:** CI passes on push.
