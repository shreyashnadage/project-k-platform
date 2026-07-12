# ADR-003: Content-Addressed Decision Receipts with Hash-Chained Audit Ledger

## Status
**Accepted**

## Context
As a DDP on OCEN, we must prove which rule version, applied to which input, produced which derived-data output, and when. This is the audit backbone for regulatory compliance and lender trust.

## Decision
Every rule evaluation (D0–D3) produces a **signed, content-addressed DecisionReceipt** that is:
1. **Content-addressed:** ruleset identified by SHA-256 of its canonical JSON; input identified by SHA-256 of its canonical JSON
2. **Signed:** HMAC in dev, AWS KMS asymmetric signature in production
3. **Hash-chained:** h_n = SHA-256(receipt_bytes ‖ h_{n-1}), creating a tamper-evident sequence
4. **Event-sourced:** written to the Redpanda trade-event stream as a `LOAN_DECISION_EVALUATED` event
5. **Persisted:** stored in the `audit.decision_receipts` Postgres table

## Verification
- Any party can verify a single receipt by recomputing its signature
- Chain integrity is verified by replaying h_n = SHA-256(receipt_n ‖ h_{n-1}) and comparing
- Ruleset provenance is verified by comparing the stored hash against the JDM file in the git commit at the stated timestamp

## Why not blockchain
- A signed hash chain in Postgres/Redpanda provides the same tamper-evidence guarantees for a single-writer system (us)
- No consensus overhead, no gas fees, no external dependency
- Sufficient for regulatory audit; blockchain adds nothing here

## Consequences
- `libs/audit/receipts.py` implements ReceiptSigner and ChainVerifier
- Every Temporal activity that evaluates a rule MUST create and persist a receipt
- Receipts are immutable — never updated, only appended
- KMS key rotation requires re-signing (or dual-signing during rotation window)
