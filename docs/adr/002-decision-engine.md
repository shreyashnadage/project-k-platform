# ADR-002: GoRules Zen Engine for Stateless Decisioning, In-Process with Temporal Workers

## Status
**Accepted**

## Context
The origination pipeline requires stateless point-evaluations at four decision gates (D0–D3). These must be:
- Externalized (not hardcoded in workflow logic)
- Versioned and content-addressed (for DDP audit)
- Called from Temporal activities (never workflow code, to preserve determinism)
- Fast (<10ms per evaluation)

Options evaluated:
1. **GoRules Zen Engine** — MIT, Rust core, Python/Node/Go bindings, JSON Decision Model (JDM)
2. **Drools/Kogito** — Apache 2.0, JVM, DMN standard, RETE inference
3. **Custom Python rule engine** — build from scratch

## Decision
Adopt **GoRules Zen Engine** with Python bindings, running **in-process** inside Temporal worker activities.

## Rationale
- **In-process:** Zen's Python bindings call the Rust core via FFI — no extra service, no network hop, no JVM to operate. Sub-millisecond evaluation.
- **Python-first:** Our Temporal workers are Python. Zen runs natively; Drools would require a separate JVM service and REST calls from every activity.
- **MIT licence:** Clean, no copyleft concerns.
- **Content-addressable:** JDM files are JSON — easily hashed, git-versioned, diffed.
- **Business-editable:** GoRules provides an open-source visual editor for JDM files.

## Why not Drools/Kogito
- Requires a JVM sidecar or separate service — operational burden for a 3-person team
- RETE inference is overkill for decision tables and simple expression evaluation
- DMN standard portability is speculative value; no lender or regulator currently requires it

## Tripwire to reconsider
- If lenders or regulators mandate DMN-standard decision models
- If we move to JVM Temporal workers (removes Zen's main advantage)
- If we need true forward-chaining inference over large rule sets (RETE)

## Consequences
- Decision tables live in `rules/*.json` and are git-versioned
- Each evaluation produces a signed DecisionReceipt (see ADR-003)
- Rule changes deploy as new JDM files — no worker redeploy needed (hot-reload via `engine.reload()`)
- Activities call `ZenDecisionEngine.evaluate()` and wrap the result in a receipt
