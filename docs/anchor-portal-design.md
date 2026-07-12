# Anchor Portal — Groundwork Review

**Status: deferred by design.** No screens, no new repo, no endpoints ship in this pass. This document is the design-review checkpoint the plan calls for — confirming the identity/RBAC groundwork already laid doesn't block adding a real anchor self-service portal later, without a second identity migration.

## What already reserves space for this

1. **Kratos identity schema** (`infra/docker/kratos/identity.schema.json`) already includes `org_type` with `enum: ["vendor", "anchor"]`, default `vendor`. An anchor identity is a first-class case in the same schema as a vendor — not a bolt-on.
2. **`identity.yaml`'s `org_type_registry`** already has both entries:
   ```yaml
   org_type_registry:
     vendor:
       description: "MSME vendor/borrower — loan applicant"
       ciam_schema: borrower
     anchor:
       description: "Anchor MSME — provides Kind 1 attestation"
       ciam_schema: borrower
   ```
   Both share the same `borrower` Kratos schema — an anchor and a vendor are the same *kind* of identity (a business entity authenticating via phone/OTP), just with a different `org_type` trait and, eventually, different permitted actions.
3. **`TokenClaims.org_type`** (`libs/auth/types.py`) is already a typed field (`OrgType` enum: `vendor` | `anchor`) on the shared token-claims type — any endpoint that eventually needs to branch on "is this caller an anchor" has the field available today, decoded consistently regardless of provider.

## What's genuinely new when the portal is built

- **A distinct role**, tentatively `anchor-self-service` (not yet added anywhere, since it has zero endpoints to gate — adding it now would be a name with no meaning). This is **not** the same as the existing ops-side `anchor-manager` Keycloak role, which is for *ops staff* managing anchors on their behalf — `anchor-self-service` would be for the anchor's own staff logging in directly.
- **New endpoints** an anchor would actually use, none of which exist today:
  - View invoices raised against them by their vendors, and each invoice's Kind 1 attestation status (IRN/IMS/routing) — read-only, scoped to their own `anchor_gstin` (the RLS groundwork from Phase 2 already isolates `loan_applications` by `anchor_gstin`, so this query pattern is already safe to build on).
  - View their vendor network — which MSME vendors have financing tied to their invoices.
  - Take the actual attestation action themselves (today, Kind 1 attestation flows entirely through the GST portal's IMS — an anchor "accepting" an invoice happens on GSTN's own systems, not ours; a portal action here would only ever be a *view* of that state, not a way to bypass GSTN).
- **A UI** — no repo exists. Given the Kratos schema is shared with the borrower PWA, the pragmatic choice when this is prioritized is likely a new route tree inside `project-k-borrower-app` (same CIAM, same session shape, different `org_type`-gated views) rather than a fourth separate frontend repo — but that's a call to make when there's an actual product spec, not now.

## Why this is deferred

Per the user's own instruction when this plan was approved: no anchor screens are designed now. Anchors remain fully passive (GST IMS actions + ops-managed onboarding via `/ops/anchor/onboard`) until there's a concrete product requirement. This document exists so that requirement, whenever it arrives, doesn't require re-litigating the identity architecture — only adding the role, the endpoints, and the UI.
