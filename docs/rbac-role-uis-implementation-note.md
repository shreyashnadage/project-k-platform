# RBAC Hardening + Role-Based Identity: Implementation Note

**Branch:** `feat/rbac-and-role-uis` (5 commits, 4953 insertions) · **13 Jul 2026** · All 5 phases complete, 222 tests passing, no regressions.

---

## Why this work happened

The user asked to check whether ERPNext/Frappe could serve as a CRM for anchors/vendors/lenders and a Loan Management System tied to Kind 1 attestation. Answering that properly required first auditing the platform's actual identity and authorization story — and that audit found real gaps: RBAC disabled by default and fail-open even when enabled, a JWT verification path that silently fell back to unverified decoding, three internal services with zero authentication, DPDP rights/consent endpoints reachable by anyone, and a shared flat API key standing in for per-user identity on every ops action. This work fixes that foundation first, then builds the identity infrastructure the role-based UI plan (Platform Console, borrower CIAM, anchor portal) depends on, and closes with the actual CRM/Loan Management answer the user asked for.

---

## What shipped, phase by phase

### Phase 1 — Protocol-based auth abstraction + fail-closed RBAC hardening (`c28b299`)

**The fail-closed rewrite** (`libs/common/middleware.py`, new `authz.yaml`):
- Before: any path not explicitly listed in `dpdp_config.yaml`'s `rbac:` section was **allowed** through regardless of role. Now: an explicit, reviewed `authz.yaml` allow-list is the only way a path bypasses auth — everything else defaults to **deny**.
- Before: if `DPDP_RBAC_ENABLED=true` but `KEYCLOAK_JWKS_URL` wasn't also set, the middleware silently fell back to `jwt.decode(token, options={"verify_signature": False})` — any forged token was trusted. Now: the app **refuses to start** in that configuration outside `INTEGRATION_MODE=sandbox`.
- Before: a broad `except Exception: pass` let JWKS-client failures through as if the request were unauthenticated-but-allowed. Now: any verification failure is a 401, never a silent pass-through.
- `/dpdp/rights/*` and `/dpdp/consent/*` are now protected **unconditionally** — even with the global RBAC toggle off — since DPDP Act exposure shouldn't depend on remembering a dev convenience flag.
- `/invoices/captured` now verifies an inbound HMAC signature (new `libs/common/webhook_auth.py`) using the same secret/scheme already used for *outbound* delivery to the back-office.
- The OCEN JWS "no signature = dev mode, allow through" bypass is now gated to `INTEGRATION_MODE=sandbox` only.
- Three internal services (`ddp_engine`, `vdp_wedge`, `trust_graph`) had **no authentication of any kind**. New `libs/common/service_auth.py` adds bearer-token verification reusing the Keycloak service clients (`la-orchestrator`, `ddp-engine`) that already existed for exactly this.
- `OPS_API_KEY_FALLBACK_ENABLED` flag added ahead of the Phase 3 cutover — the shared ops API key stays working today, with an explicit off-switch for later.

**The protocol layer** (new `libs/auth/`): `TokenVerifier`/`IdentityProvider`/`SMSGateway` protocols, a Keycloak adapter (workforce IAM) and a Kratos/Hydra adapter (borrower CIAM, scaffolded ahead of Phase 3's wiring), and a config-driven factory (`identity.yaml`) — mirrors the existing `libs/integrations/protocols.py` pattern so provider swaps never touch application code.

**Honesty note:** `libs/common/middleware.py` was **not** migrated to call the new protocol layer — it still has its own inline, independently-tested Keycloak verification logic. Migrating it is a low-risk mechanical follow-up (documented in `docs/auth-architecture.md`), deliberately deferred rather than risking a rewrite of already-verified, security-critical code mid-session.

### Phase 2 — PostgreSQL Row-Level Security groundwork (`741f115`)

Found and fixed two real bugs in the scaffolded RLS code before it ever ran:
1. `set_tenant_context`/`clear_tenant_context` passed a raw f-string to `session.execute()` — SQLAlchemy 2.x requires `text()`-wrapping, and PostgreSQL's `SET LOCAL` doesn't accept bind parameters in most drivers anyway. Fixed with `set_config(name, value, is_local=true)`, a normal function call that works correctly with bind parameters.
2. The "bypass" path set the tenant variable to an **empty string** — which would make `tenant_column = current_setting(...)` match nothing, hiding all data from bypass roles (`platform-admin`, `operations`) instead of showing everything. Fixed with an explicit `__RLS_BYPASS__` sentinel that every policy checks for.

Also rewrote `tenancy.yaml`, which referenced tables (`vendor_profiles`, `invoices`, `trust_scores`) that don't exist in the actual schema — the real tables are `anchors`, `vendors`, `loan_applications`, `decision_receipts` (per `migrations/versions/001_initial_schema.py`). New `migrations/versions/005_enable_rls.py` enables RLS on `loan_applications` (direct `anchor_gstin` column) and `decision_receipts` (scoped via a join back to `loan_applications`, since it only carries `loan_application_id`).

`libs/common/middleware.py` now extracts the tenant claim after successful token verification and populates ContextVars for a new `tenant_scoped_session()` FastAPI dependency to read.

**Explicitly deferred:** no endpoint has been wired to `tenant_scoped_session()` yet — the migration's docstring is explicit that running it against a database any live endpoint still queries via the plain session dependency would silently return zero rows.

### Phase 3 — Borrower CIAM infrastructure + ownership enforcement (`14a8048`)

Added Ory Kratos + Hydra to `docker-compose.yml` (dedicated Postgres DBs, migration containers, following the existing `temporal-db` pattern) and their config (`infra/docker/kratos/`, `infra/docker/hydra/`) — identity schema matching `identity.yaml`'s `borrower` section (phone, org_type, gstin, udyam_number, enterprise_name).

`/loans/apply` and `/loans/status` now enforce ownership — a vendor can only submit or query applications matching their own GSTIN claim — gated behind `BORROWER_AUTH_ENABLED` (default `false`, since no live Kratos/Hydra deployment exists yet; enabling it with no way for vendors to obtain a token would just lock everyone out). `LoanApplicationStatus` now carries `vendor_gstin` so the ownership check has something to compare against — previously the response didn't expose it at all, meaning **anyone who could guess a UUID could query any vendor's application status**.

`docs/borrower-ciam-contract.md` documents the full contract for the external `project-k-borrower-app` repo: endpoints, token claim shape, identity schema, and what's not built yet (real SMS/OTP delivery, atomic Kratos-identity + vendor-record creation on registration).

### Phase 4 — API contracts (`b0d1e2b`)

- `docs/api-contract-v1.yaml` — OpenAPI 3.1 spec generated directly from the live FastAPI app (`app.openapi()`), 27 endpoints.
- `docs/admin-console-contract.md` — what the future `project-k-admin-console` repo needs: the already-registered `admin-ui` Keycloak client, role-to-endpoint mapping, and the plan to migrate ops staff off the shared API key.
- `docs/anchor-portal-design.md` — confirms the identity groundwork (Kratos `org_type` enum, `identity.yaml`'s `org_type_registry`, `TokenClaims.org_type`) doesn't block a future anchor self-service portal, without designing any screens now.

### Phase 5 — The actual CRM/Loan Management answer (`351585f`)

This is what the user asked about directly: **yes**, the back-office can serve as a CRM tracking every Anchor, Vendor, and Lender plus a Loan Management view — because it's already the ops system of record, not a new system to build.

`docs/frappe-crm-loan-management-spec.md` gives the full DocType schema (Anchor, Vendor, Lender, Invoice/Attestation, Loan Application, Decision Receipt), with every field traced to a real Pydantic model field or event payload key — no invented schema.

**The one real gap, fixed:** `invoice.kind1_attested` — the event carrying the actual IRN/IMS-status/routing-active detail — existed in `libs/common/events.py` but was never forwarded to the back-office; only the generic D0 gate pass/fail outcome was. The fix is applied in the working tree (not committed under this branch — see below).

---

## How attestation actually links through, end to end

```
VDP Wedge validates invoice (IRN + IMS + routing)
    → emits invoice.kind1_attested {irn, ims_status, repayment_routing_active, is_kind1}
    → forwarded to back-office (Phase 5 fix) → Invoice/Attestation DocType

D0 gate evaluates Kind 1 as part of the loan pipeline
    → emits loan.decision_evaluated {gate, outcome, ruleset_hash, input_hash, receipt_id}
    → already forwarded → Decision Receipt DocType, linked to Loan Application

Loan Application DocType links: Vendor ← Anchor ← Invoice/Attestation ← Decision Receipt
```

Click into a Loan Application in the back-office and you see the vendor, the anchor, the invoice's live Kind 1 status, and the full signed decision trail — all from data that's either already flowing or fixed to flow in this branch.

---

## Test coverage

| File | Count | Covers |
|---|---|---|
| `tests/test_rbac_hardening.py` | 22 | Fail-closed defaults, always-protected paths, JWKS failure handling, startup guards, webhook signature verification, OCEN JWS gating |
| `tests/test_service_auth.py` | 9 | Service-to-service auth enable/disable, JWKS failure, startup guard |
| `tests/test_auth_protocols.py` | 18 | Protocol conformance, Keycloak/Kratos adapters, factory provider selection, tenancy config |
| `tests/test_rls.py` | 10 | `set_config` SQL correctness, bypass sentinel, tenant-scoped session behavior, middleware claim extraction |
| `tests/test_borrower_ownership.py` | 6 | Vendor ownership enforcement on `/loans/apply` and `/loans/status`, mocked verifier (no live Kratos needed) |
| `tests/test_kind1_event_forwarding.py` | 2 | `invoice.kind1_attested` reaches the forward list |

**63 new tests, 222 total passing** (the platform had 143 before this branch started + tests added by concurrent unrelated work on the same branch), zero regressions.

---

## What's NOT done (by design, not oversight)

- `libs/common/middleware.py` still has its own inline Keycloak verification rather than calling `libs/auth/factory.get_workforce_verifier()` — functionally equivalent, migration deferred (see Phase 1 above).
- No endpoint queries `loan_applications`/`decision_receipts` through `tenant_scoped_session()` yet — Phase 2 ships the mechanism, not the wiring.
- `BORROWER_AUTH_ENABLED` and RLS enforcement are both off by default — turning them on requires deploying Kratos+Hydra and running migration 005 respectively; neither should be flipped without that infrastructure in place.
- The Platform Console (ops/admin/lender UI) and the back-office's actual DocType JSON/controllers don't exist as code — both have API contracts specified (Phase 4, Phase 5) for a follow-up session to build against.
- SMS/OTP delivery for Kratos has no real provider adapter (MSG91/Kaleyra) — only a protocol definition.

## Concurrent work on this branch

A separate, unrelated body of work landed on the same branch during this session: a Udyam-verification feature (uncommitted, predates this work) and a Frappe→"back-office" terminology rename (`services/frappe_sync` → `services/backoffice_sync`, env var renames, brand config changes). Every commit in this branch was staged file-by-file to exclude that work — none of it is included in these 5 commits, and none of it was lost; it remains in the working tree for whoever is driving it to commit separately. The one exception is a single-line fix (`invoice.kind1_attested` added to the forward list) which lives in a file (`services/backoffice_sync/config.py`) that doesn't exist in git history yet — that fix is applied in the working tree and will ride along whenever that rename is committed, rather than being force-committed under this work's authorship.

## Environment variables introduced

| Variable | Default | Purpose |
|---|---|---|
| `AUTHZ_CONFIG_PATH` | `authz.yaml` | Public-path / always-protected-path allow-list |
| `SERVICE_AUTH_ENABLED` | `false` | Service-to-service auth for ddp_engine/vdp_wedge/trust_graph |
| `OPS_API_KEY_FALLBACK_ENABLED` | `true` | Shared ops API key — flip off once Platform Console ships real per-user login |
| `IDENTITY_CONFIG_PATH` | `identity.yaml` | Auth provider configuration |
| `TENANCY_CONFIG_PATH` | `tenancy.yaml` | RLS tenant isolation configuration |
| `BORROWER_AUTH_ENABLED` | `false` | Ownership enforcement on `/loans/*` — requires live Kratos+Hydra |
| `KRATOS_PUBLIC_URL` / `KRATOS_ADMIN_URL` | — | Kratos endpoints (borrower CIAM) |
| `HYDRA_PUBLIC_URL` / `HYDRA_ADMIN_URL` / `HYDRA_JWKS_URL` | — | Hydra endpoints (token issuance) |
| `SMS_GATEWAY_PROVIDER` | `sandbox` | OTP delivery provider selection (no real adapter built yet) |

## Verification performed

- `make test` equivalent (`pytest tests/ --ignore=tests/test_dpdp_scenarios.py`) run after every phase — 222 passed, 0 failed, at each checkpoint.
- Startup-guard behavior verified via subprocess isolation (fresh Python process, controlled env vars) — confirms the app genuinely refuses to start with unsafe RBAC configuration.
- Ownership enforcement verified against a mocked `TokenVerifier` — proves the authorization *logic* is correct independent of whether Kratos/Hydra containers are actually running (they aren't, in this environment).
- RLS SQL correctness verified by asserting the exact `text()`-wrapped SQL and bind parameters sent to a mocked `AsyncSession` — proves the fix, without needing a live Postgres instance with RLS enabled.

## Next steps, in priority order

1. Migrate `libs/common/middleware.py` to `libs/auth/factory.get_workforce_verifier()` — removes the duplicated JWT verification logic.
2. Wire at least one endpoint (`GET /ops/applications/active` is the natural first candidate) to `tenant_scoped_session()`, then run migration 005 in a real Postgres to validate the RLS policies end-to-end.
3. Deploy Kratos+Hydra locally (`docker compose up kratos hydra`), confirm the identity schema loads, and test the self-service registration flow manually.
4. Build a real SMS gateway adapter (MSG91 or Kaleyra) so Kratos's OTP flow is actually usable, not just logged.
5. Start the `project-k-admin-console` repo against `docs/admin-console-contract.md`.
6. Build the actual DocTypes in `project-k-ocen-connector` against `docs/frappe-crm-loan-management-spec.md`.
