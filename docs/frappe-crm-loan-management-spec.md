# Back-Office CRM + Loan Management System — DocType Spec (Phase 5)

**For:** the external `project-k-ocen-connector` repo (the Frappe/ERPNext custom app that receives platform webhooks — referred to elsewhere as the back-office/Munimco Ops connector). This document is a schema **spec**, not implementation — no DocType JSON or controller code ships from this repo. Building the actual DocTypes is a follow-up session against that repo.

**Correction (reconciled against the live deployment):** an earlier version of this spec proposed a from-scratch `Loan Application` DocType. That name collides with Frappe's *official* Lending app (`frappe/lending`, GPLv3), which is genuinely installed alongside the connector on the live Frappe site — confirmed directly on the server, not assumed. The connector as actually built (`ocen_ops/lending/lifecycle.py`) already avoided this collision: it stages platform events in a custom `OCEN Loan Application` DocType, then creates/links real `Loan Application` → `Loan` → `Loan Disbursement` → `Loan Repayment` records in Frappe Lending's own schema once an offer is accepted. The spec below reflects that actual architecture, not the original from-scratch proposal. See "Loan Application" below for the full mapping.

## Why this exists

The back-office (Frappe/ERPNext) is already the ops/admin system of record — ops staff work entirely inside it today (per `docs/user-guide-by-role.md`). Extending it with CRM-style tracking of every Anchor, Vendor, and Lender, plus a Loan Management view showing loan flows and Kind 1 attestation status, is a natural extension of what's already there — not a new system, and not the Platform Console (which is the *action* surface, per `docs/admin-console-contract.md`; this is the *record-keeping and reporting* surface, same split as today).

## What already reaches the back-office (confirmed, not assumed)

`services/backoffice_sync/config.py`'s `EVENTS_TO_FORWARD` set determines what's delivered via signed webhook to `ocen_ops.api.receive_platform_webhook`. As of this phase:

```
invoice.kind1_attested        ← added in this phase (see below)
loan.application_created
loan.decision_evaluated
loan.submitted_to_lender
loan.offer_received
loan.offer_accepted
loan.disbursed
loan.repayment_observed
loan.closed
loan.rejected
vendor.onboarded
vendor.invited
vendor.activated
anchor.onboarded
ops.hold_applied
ops.hold_released
ops.flag_added
ops.escalated
```

**The gap this phase closes:** `invoice.kind1_attested` (defined in `libs/common/events.py` as `EventType.INVOICE_KIND1_ATTESTED`, emitted per `services/vdp_wedge/service.py`'s Kind 1 check) existed but was never forwarded. Before this fix, the back-office only ever saw the *generic* D0 gate outcome via `loan.decision_evaluated` (`gate="d0-kind1-gate"`, `outcome="pass"|"fail"|"flag"`) — never the underlying IRN, IMS status, or repayment-routing detail that explains *why*. Now it does.

## DocType schema

Field names below come directly from `libs/common/models.py` (the canonical Pydantic models) and the event payloads in `libs/common/events.py` — not invented. Types are named the way Frappe itself names them (Data, Link, Check, Currency, etc.) for direct translation into DocType JSON.

### Anchor

| Field | Frappe type | Source |
|---|---|---|
| `name` (Frappe's own primary key, autoname) | — | `AnchorProfile.name` |
| `gstin` | Data (15 char) | `AnchorProfile.gstin.value` |
| `sector` | Data | `AnchorProfile.sector` |
| `region` | Data | `AnchorProfile.region` |
| `repayment_routing_active` | Check | `AnchorProfile.repayment_routing_active` |
| `onboarded_at` | Datetime | `AnchorProfile.onboarded_at` |

Populated from: `anchor.onboarded` event.

### Vendor (Borrower)

| Field | Frappe type | Source |
|---|---|---|
| `name` | Data | `VendorProfile.name` |
| `gstin` | Data (15 char) | `VendorProfile.gstin.value` |
| `udyam_number` | Data | `VendorProfile.udyam_number` |
| `udyam_category` | Select (micro/small/medium) | `VendorProfile.udyam_category` |
| `anchors` | Table MultiSelect / child table | `VendorProfile.anchor_ids` → link to Anchor DocType |
| `onboarded_at` | Datetime | `VendorProfile.onboarded_at` |

Populated from: `vendor.onboarded`, `vendor.invited`, `vendor.activated` events.

### Lender

Not currently modeled as a platform-side Pydantic entity (lenders are OCEN network participants, identified by ID in `matched_lender_ids`/`selected_lender_id`). Minimal DocType:

| Field | Frappe type | Source |
|---|---|---|
| `lender_id` | Data | `LoanApplication.selected_lender_id` / OCEN participant ID |
| `lender_name` | Data | Manually maintained (no event carries a display name today) |

This DocType is a placeholder for reporting joins — populate manually until the platform has a real Lender entity to source from (see `libs/common/models.py`'s `LenderFilter` for what *eligibility* data exists, which is a different thing from an onboarded-lender directory).

### Invoice / Attestation

| Field | Frappe type | Source |
|---|---|---|
| `irn` | Data (64 char) | `invoice.kind1_attested` payload: `irn` |
| `vendor_gstin` | Data, Link to Vendor | `invoice.kind1_attested` payload (via join on loan application) |
| `anchor_gstin` | Data, Link to Anchor | same |
| `ims_status` | Select (accepted/rejected/pending/deemed_accepted) | payload: `ims_status` |
| `repayment_routing_active` | Check | payload: `repayment_routing_active` |
| `is_kind1` | Check | payload: `is_kind1` |
| `loan_application` | Link to Loan Application | join key |

Populated from: `invoice.kind1_attested` (newly forwarded this phase).

### Loan Application (staging) + real Frappe Lending records

Two layers, matching what's actually deployed — not a single flat DocType:

**1. `OCEN Loan Application`** (custom staging DocType — every platform event lands here first, regardless of whether an offer is ever accepted):

| Field | Frappe type | Source |
|---|---|---|
| `application_id` | Data (UUID) | `LoanApplication.id` |
| `vendor` | Link to Vendor | `LoanApplication.vendor_id` |
| `anchor` | Link to Anchor | `LoanApplication.anchor_id` |
| `invoice` | Link to Invoice / Attestation | `LoanApplication.invoice_id` |
| `requested_amount` | Currency | `LoanApplication.requested_amount` |
| `requested_tenor_days` | Int | `LoanApplication.requested_tenor_days` |
| `status` | Select (matches `LoanApplicationStatus` enum values) | `LoanApplication.status` |
| `current_gate` | Data | forwarded gate string, e.g. `d0-kind1-gate` |
| `matched_lender_ids` | Table MultiSelect | `LoanApplication.matched_lender_ids` |
| `selected_lender` | Link to Lender | `LoanApplication.selected_lender_id` |
| `offer_data` | JSON | raw `LoanApplication.offer` payload, before it's split into a real Loan |
| `amount_sanctioned` | Currency | set once a real `Loan` is created (below) |
| `linked_loan_application` | Link to (real) Loan Application | set by `create_loan_from_offer` |
| `linked_loan` | Link to (real) Loan | set by `create_loan_from_offer` |
| `ops_hold` | Check | from `ops.hold_applied` / `ops.hold_released` events |
| `ops_flags` | Table (child, one row per `ops.flag_added` event) | flag_type, note, flagged_by |

Populated from: `loan.application_created`, `loan.submitted_to_lender`, `loan.offer_received`, `loan.rejected`, `ops.hold_applied`, `ops.hold_released`, `ops.flag_added`, `ops.escalated`.

**2. Real Frappe Lending records** — created only once an offer is accepted, via `ocen_ops/lending/lifecycle.py`'s `create_loan_from_offer` / `create_disbursement` / `create_repayment` / `close_loan`:

| Event | Frappe Lending action | Real DocType touched |
|---|---|---|
| `loan.offer_accepted` | `create_loan_from_offer` — creates + submits a `Loan Application`, then a `Loan` (status `Sanctioned`) | `Loan Application`, `Loan`, `Loan Type` (auto-created: "OCEN Vendor Receivable"), `Customer` (auto-created from vendor GSTIN if none exists) |
| `loan.disbursed` | `create_disbursement` | `Loan Disbursement` (`against_loan` = the `Loan` above) |
| `loan.repayment_observed` | `create_repayment` | `Loan Repayment` |
| `loan.closed` | `close_loan` — sets `Loan.status = "Closed"` | `Loan` |

These are Frappe Lending's own real schema (`applicant_type`/`applicant`, `loan_product`, `loan_amount`, `rate_of_interest`, `repayment_method`, etc.) — not custom fields. `OCEN Loan Application.linked_loan_application`/`linked_loan` are the join keys back to the staging record above.

### Decision Receipt (read-only, audit)

| Field | Frappe type | Source |
|---|---|---|
| `loan_application` | Link to Loan Application | `DecisionReceipt.loan_application_id` |
| `gate` | Data | `DecisionReceipt.gate` |
| `outcome` | Select (pass/fail/flag) | `DecisionReceipt.outcome` |
| `ruleset_hash` | Data (64 char) | `DecisionReceipt.ruleset_hash` |
| `input_hash` | Data (64 char) | `DecisionReceipt.input_hash` |
| `engine_version` | Data | `DecisionReceipt.engine_version` |
| `evaluated_at` | Datetime | `DecisionReceipt.evaluated_at` |

Populated from: `loan.decision_evaluated`. **Updated:** the payload now also carries `signature` and `chain_hash` — `evaluate_decision` (`services/la_orchestrator/activities.py`) was fixed to actually sign and persist every receipt via `ReceiptSigner`/`ChainVerifier` (previously it computed an ad-hoc, non-reproducible hash and never signed anything at all — the `decision_receipts` table was permanently empty). Add `signature`/`chain_hash` as two more Data columns on this DocType if full chain-verification inside the back-office UI is wanted; the platform's own audit trail is real now either way (queryable via `GET /dpdp/audit/receipts/{loan_application_id}`).

## What the connector repo's `receive_platform_webhook` handler needs to do

For each event type in `EVENTS_TO_FORWARD`, map its payload fields onto the DocType fields above (mostly 1:1, per the tables). This is a mechanical translation exercise once the DocTypes exist — the mapping is fully specified above so it doesn't require re-deriving field names from the platform source a second time.

## Explicitly out of scope for this phase

- Actual DocType JSON fixtures or Python controllers (belongs in `project-k-ocen-connector`).
- The `Lender` DocType's data source (no platform-side lender directory exists yet to sync from).
- Adding `signature`/`chain_hash` columns to the Decision Receipt DocType itself (the event payload now carries both — this is a connector-repo DocType change, not a platform one).
