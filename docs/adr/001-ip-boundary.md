# ADR-001: IP Boundary Between GPL Systems-of-Record and Proprietary Trust Graph

## Status
**Accepted**

## Context
We use GPL-licensed ERPNext/Frappe (Phase 1 VDP wedge) and potentially AGPL Frappe Lending. GPL/AGPL copyleft requires derivative works to be distributed under the same licence. Our proprietary Trust Graph, decision engine integration, and DDP attestation layer are the company's core intellectual property and must remain proprietary.

## Decision
Enforce a hard **IP boundary** between GPL/AGPL systems-of-record and proprietary code. The two sides communicate **only** via:
1. REST APIs (HTTP/JSON)
2. Redpanda event bus (Kafka protocol)

**Never** via code linking, shared libraries, in-process calls, or shared database schemas.

## Consequences
- ERPNext/Frappe apps can be freely extended with custom Frappe apps (also GPL) without affecting proprietary code.
- Apache Fineract (Apache-2.0) is permissive and could technically be linked, but we keep it below the boundary anyway for clean separation.
- The event bus is the integration spine — domain events flow up, commands flow down.
- Each side has its own database schema; no shared tables.
- Pin exact commit licences for Frappe repos (GPL vs AGPL ambiguity is real).

## Risks
- AGPL's "network interaction" clause is broader than GPL's distribution trigger. If Frappe apps are served over a network, AGPL may require source disclosure of the *Frappe app itself* — but not of the proprietary services on the other side of the API boundary.
- Monitor Frappe licence changes closely.
