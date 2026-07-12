# Platform Console API Contract

**For:** the future `project-k-admin-console` repo — a Next.js app for Ops staff, Admins, and Lender analysts, authenticated against Keycloak.

**Status:** the backend side of this contract (Keycloak realm, RBAC-hardened `/ops/*` and `/dpdp/*` endpoints, protocol-based token verification) is built and tested. The console app itself has not been scaffolded — this document exists so that work can start without re-deriving the auth flow.

---

## Authentication

**OIDC discovery URL (local dev):** `http://localhost:8080/realms/ocen-platform/.well-known/openid-configuration`

**Client:** `admin-ui` — already registered in `infra/docker/keycloak-realm.json`:
- Public client (no client secret — browser-based OAuth2 Authorization Code + PKCE flow)
- `redirectUris`: `http://localhost:3000/*`
- `webOrigins`: `http://localhost:3000`

**Flow:** standard OAuth2 Authorization Code + PKCE against Keycloak, then send the resulting access token as `Authorization: Bearer <token>` on every API call.

**Seeded users (local dev):** currently only one — `admin` / `admin_dev`, role `platform-admin`. No users exist yet for `operations`, `anchor-manager`, or `lender-viewer` — these need to be created (via Keycloak admin console or realm-import update) before a console session for those roles can be tested end-to-end.

## Roles and what each can do

| Role | Endpoint access |
|---|---|
| `platform-admin` | Everything below, plus `/dpdp/rights/*` and `/dpdp/consent/*` |
| `operations` | `/ops/hold`, `/ops/release`, `/ops/flag`, `/ops/escalate`, `/ops/applications/*` |
| `anchor-manager` | `/ops/vendor/invite`, `/ops/anchor/onboard`, `/ops/applications/*` |
| `lender-viewer` | `/ops/applications/*` (read-only — no mutating endpoints allowed) |

Exact mapping lives in `dpdp_config.yaml`'s `rbac:` section — this is the single source of truth; the table above is a summary, not a second copy to keep in sync by hand.

## Token claim shape

Standard Keycloak realm-role JWT:

```json
{
  "sub": "<keycloak user id>",
  "iss": "http://keycloak:8080/realms/ocen-platform",
  "realm_access": { "roles": ["operations"] },
  "email": "ops.user@example.com"
}
```

Decoded by `KeycloakTokenVerifier` (`libs/auth/adapters/keycloak.py`) into a provider-agnostic `TokenClaims` — the console never needs to know about Keycloak's specific claim nesting if it calls through the platform's own endpoints (it only matters if the console independently decodes tokens client-side for UI purposes, e.g. to show "logged in as ops.user@example.com").

## Full endpoint list

See `docs/api-contract-v1.yaml` (generated from the live FastAPI app via `app.openapi()`) for the complete, authoritative request/response schema of every endpoint. The `/ops/*` and `/dpdp/*` groups are what this console wraps.

## Real per-user identity, not the shared API key

Historically, `/ops/*` endpoints accepted a single shared `OPS_API_KEY` with no per-user identity — `held_by`/`flagged_by`/etc. fields were free-text strings supplied by the caller, not verified claims. The Platform Console is the intended cutover point: once it's live, ops staff log in individually via Keycloak, and those free-text fields should be populated from the verified token's `email`/`sub` claim rather than trusted client input. `OPS_API_KEY_FALLBACK_ENABLED` (`services/borrower_gateway/ops_api.py`) exists specifically to be flipped to `false` once that cutover is complete.

## What's NOT built yet

- The console app itself (no repo exists).
- Real per-role seed users beyond the single `admin` account.
- Any UI wiring of `held_by`/`flagged_by` etc. to the verified token identity instead of free-text — that's an `ops_api.py` change to make once the console exists and can be tested against it.
