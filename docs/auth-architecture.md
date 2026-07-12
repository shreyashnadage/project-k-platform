# Authentication & Authorization Architecture

## Overview

The platform uses a **protocol-based, config-driven** identity layer with three distinct domains:

| Domain | Who | Provider | Config |
|--------|-----|----------|--------|
| Workforce IAM | Ops, admins, lender analysts | Keycloak | `identity.yaml` → `workforce` |
| Borrower CIAM | Vendors, anchors (future) | Ory Kratos + Hydra | `identity.yaml` → `borrower` |
| Lender M2M | Lender backend systems | OAuth2 + JWS (RFC 7797) | OCEN protocol spec |

## Protocol Abstraction

Application code never imports provider-specific SDKs. All auth goes through:

```
libs/auth/protocols.py    → TokenVerifier, IdentityProvider, SMSGateway
libs/auth/factory.py      → get_workforce_verifier(), get_borrower_verifier()
libs/auth/adapters/       → keycloak.py, kratos.py (+ future: auth0.py, zitadel.py)
```

To swap providers: change `identity.yaml` → `provider` field. Zero application code changes.

## Config Files

| File | Purpose |
|------|---------|
| `authz.yaml` | Public path allow-list, always-protected paths |
| `identity.yaml` | Provider URLs, algorithms, claim paths, org types |
| `tenancy.yaml` | RLS policies, tenant claim path, bypass roles |
| `dpdp_config.yaml` | PII fields, retention, RBAC role→endpoint map |

## RBAC Posture

**Default: DENY.** When `DPDP_RBAC_ENABLED=true`:
1. Path in `authz.yaml` → `public_paths`? → Allow (no token needed)
2. Path in `authz.yaml` → `always_protected_paths`? → Token required even if RBAC disabled
3. All other paths: Bearer token required, roles checked against `dpdp_config.yaml` → `rbac`
4. No matching role entry? → 403

## Multi-Tenancy (PostgreSQL RLS)

Tenant isolation at the database level:
1. JWT verified → tenant claim (`org_id`) extracted
2. `SET LOCAL app.tenant_id = '{anchor_gstin}'` on DB session
3. RLS policies restrict all queries to tenant's rows
4. `platform-admin` / `operations` bypass RLS (see all data)

Config: `tenancy.yaml`

## Adding a New Auth Provider

1. Create `libs/auth/adapters/newprovider.py` implementing `TokenVerifier` (and optionally `IdentityProvider`)
2. Add provider case to `libs/auth/factory.py`
3. Add config section to `identity.yaml`
4. No other code changes needed

## Current Implementation Status (honest snapshot)

- `libs/auth/protocols.py`, `types.py`, `factory.py`, `adapters/keycloak.py`, `adapters/kratos.py` — **implemented and unit-tested** (`tests/test_auth_protocols.py`, 18 tests). This is the target architecture for any *new* auth-consuming code.
- `libs/common/middleware.py`'s `DPDPRBACMiddleware` — **not yet migrated** to call `get_workforce_verifier()`. It still verifies Keycloak JWTs with its own inline JWKS logic (functionally equivalent, independently tested in `tests/test_rbac_hardening.py`, fail-closed). The two implementations currently duplicate the same JWT/JWKS verification logic.
- Migrating `middleware.py` to consume the protocol layer is a low-risk, mechanical follow-up (swap the inline `_decode_token` for `await get_workforce_verifier().verify(token)`) — deliberately deferred rather than risking a mid-flight rewrite of already-verified, security-critical enforcement code. Do this before adding a second consumer of `TokenVerifier` (e.g. the Phase 5 Frappe integration, if it ever needs to verify tokens itself), so the duplication doesn't spread further.
- `libs/auth/adapters/kratos.py` is scaffolded ahead of schedule (by design, per its own docstring) — it is Phase 3's implementation, not wired into any running code yet.
- `libs/db/rls.py` is scaffolded for Phase 2 but not yet wired into any DB session — see Phase 2 for the fix needed in `set_tenant_context`/`clear_tenant_context` (raw SQL strings need `sqlalchemy.text()` wrapping, and `SET LOCAL` doesn't accept bind parameters in most PostgreSQL drivers — the value needs safe literal interpolation instead).
