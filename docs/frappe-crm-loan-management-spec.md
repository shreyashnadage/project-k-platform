# Back-Office CRM + Loan Management System — DocType Spec (Phase 5)

**For:** the external `project-k-ocen-connector` repo (the Frappe/ERPNext custom app that receives platform webhooks — referred to elsewhere as the back-office/Munimco Ops connector). This document is a schema **spec**, not implementation — no DocType JSON or controller code ships from this repo. Building the actual DocTypes is a follow-up session against that repo.

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

### Loan Application

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
| `offer_amount`, `offer_rate_bps`, `offer_tenor_days` | Currency / Int / Int | `LoanApplication.offer` (`LoanOffer` fields) |
| `ops_hold` | Check | from `ops.hold_applied` / `ops.hold_released` events |
| `ops_flags` | Table (child, one row per `ops.flag_added` event) | flag_type, note, flagged_by |

Populated from: `loan.application_created`, `loan.submitted_to_lender`, `loan.offer_received`, `loan.offer_accepted`, `loan.disbursed`, `loan.repayment_observed`, `loan.closed`, `loan.rejected`, `ops.hold_applied`, `ops.hold_released`, `ops.flag_added`, `ops.escalated`.

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

Populated from: `loan.decision_evaluated` (payload today carries `gate`, `outcome`, `ruleset_hash`, `input_hash`, `receipt_id` — confirmed against the actual event, not assumed). Note: `signature` and `chain_hash` exist on the `DecisionReceipt` Pydantic model but the forwarded event payload does not currently carry them — if full chain-verification is needed inside the back-office UI (as opposed to only in the platform's own audit tooling), that's an additional field to add to the event payload, out of scope here.

## What the connector repo's `receive_platform_webhook` handler needs to do

For each event type in `EVENTS_TO_FORWARD`, map its payload fields onto the DocType fields above (mostly 1:1, per the tables). This is a mechanical translation exercise once the DocTypes exist — the mapping is fully specified above so it doesn't require re-deriving field names from the platform source a second time.

## Explicitly out of scope for this phase

- Actual DocType JSON fixtures or Python controllers (belongs in `project-k-ocen-connector`).
- The `Lender` DocType's data source (no platform-side lender directory exists yet to sync from).
- Adding `signature`/`chain_hash` to the `loan.decision_evaluated` event payload (a platform-side change, not attempted here since no consumer currently needs it).
