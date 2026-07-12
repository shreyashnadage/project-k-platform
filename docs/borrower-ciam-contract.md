# Borrower CIAM Contract

**For:** the external `project-k-borrower-app` (Next.js PWA) repo, integrating with this platform's borrower/vendor identity layer.

**Status:** infrastructure scaffolded (Kratos + Hydra in `docker-compose.yml`, config in `infra/docker/kratos/` and `infra/docker/hydra/`), enforcement code paths exist in `services/borrower_gateway/app.py` but are **disabled by default** (`BORROWER_AUTH_ENABLED=false`) until this stack is actually deployed and the PWA is updated to use it. Until then, `/loans/*` and `/vendors/*` remain open exactly as they are today.

---

## Identity provider endpoints

| Purpose | URL (local dev) |
|---|---|
| Kratos public API (self-service registration/login/recovery flows) | `http://localhost:4433` |
| Kratos admin API (identity CRUD — server-to-server only, never call from the PWA) | `http://localhost:4434` |
| Hydra public API (OAuth2 token endpoint, JWKS) | `http://localhost:4444` |
| Hydra admin API (client management, consent — server-to-server only) | `http://localhost:4445` |
| JWKS (for verifying tokens, if the PWA ever needs to) | `http://localhost:4444/.well-known/jwks.json` |

## Identity schema

Registration collects these traits (`infra/docker/kratos/identity.schema.json`):

| Trait | Required | Notes |
|---|---|---|
| `phone` | Yes | Used as the login identifier; OTP-based (Kratos `code` method) |
| `org_type` | No (defaults `vendor`) | `vendor` \| `anchor` — reserved for a future anchor self-service portal |
| `gstin` | No | 15-char GSTIN, same pattern validated elsewhere in this platform |
| `udyam_number` | No | |
| `enterprise_name` | No | |

## Token claim shape

Once authenticated (Kratos session → Hydra OAuth2 code flow → access token), the platform's `KratosTokenVerifier` (`libs/auth/adapters/kratos.py`) decodes tokens into:

```json
{
  "subject": "<kratos identity id>",
  "org_id": "<if present>",
  "org_type": "vendor",
  "phone": "+919876543210",
  "raw": { "...full decoded token, including gstin if present..." }
}
```

`gstin` is read from the raw claim (`claims.raw["gstin"]`) — it is not yet promoted to a first-class `TokenClaims` field, since it's borrower-specific and the type is shared with workforce/Keycloak tokens.

## Which endpoints require a token (once `BORROWER_AUTH_ENABLED=true`)

| Endpoint | Requirement |
|---|---|
| `POST /loans/apply` | Bearer token required. `request.vendor_gstin` must equal the token's `gstin` claim — a vendor cannot submit an application for a different GSTIN. |
| `POST /loans/status` | Bearer token required. The looked-up application's `vendor_gstin` must equal the token's `gstin` claim — a vendor cannot query another vendor's application by guessing its UUID. |
| `POST /vendors/register`, `POST /vendors/activate` | Still open (pre-authentication, by definition — this is how an identity gets created in the first place). |

Until `BORROWER_AUTH_ENABLED=true`, none of the above is enforced — the endpoints behave exactly as they do today.

## What's NOT built yet

- **SMS/OTP delivery**: Kratos's `code` method needs a real SMS courier. No MSG91/Kaleyra adapter exists yet (`libs/auth/protocols.py::SMSGateway` is defined, no concrete implementation). Until one exists, OTP codes only appear in Kratos's own container logs — fine for local dev, not usable in production.
- **Atomic vendor-record + Kratos-identity creation**: `POST /vendors/register` today only creates the platform's own vendor record (in-memory or Postgres); it does not yet also call Kratos's admin API to create a matching Kratos identity. Wiring these together atomically (so a failure partway through doesn't leave an orphaned record either side) is a follow-up.
- **PWA-side integration**: this repo only defines the contract above — the actual Kratos self-service UI flows (registration/login/recovery forms) are the `project-k-borrower-app` repo's responsibility, per `README.md`'s existing description of that repo using "Ory Kratos auth with mock provider for development."

## Testing without live infrastructure

Set `BORROWER_AUTH_ENABLED=false` (the default) — the platform behaves exactly as it does today, no Kratos/Hydra required. The ownership-enforcement *logic* itself (a vendor cannot see another vendor's application) is unit-tested against a mocked verifier in `tests/test_borrower_ownership.py`, independent of whether the real Kratos/Hydra containers are running.
