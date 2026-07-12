# User Guide — OCEN Platform

## What is this?

This is a software platform that helps small businesses (MSME vendors) get quick loans against their pending invoices from larger companies (anchors/buyers).

Think of it like this: you sold goods worth 5 lakhs to a large auto company. Instead of waiting 60-90 days for payment, you can get 80-90% of that amount as a loan within hours, using this platform.

## How does it work?

### The Simple Version

1. A vendor has a confirmed invoice from a large buyer (the "anchor")
2. The vendor applies for a loan through this platform
3. The platform checks: Is the invoice real? Is the buyer going to pay? Does the vendor qualify?
4. If everything checks out, the platform sends the application to multiple lenders
5. Lenders compete to offer the best rate
6. The vendor picks an offer and gets money

### What makes this special?

The platform uses India's **OCEN 4.0** (Open Credit Enablement Network) — a government-backed protocol that lets loan agents connect to multiple lenders through a single integration. Instead of applying to banks one by one, the vendor's application goes to all eligible lenders simultaneously.

The secret sauce is **Kind 1 attestation** — the platform only sends applications where:
- The invoice has a valid e-invoice reference (IRN) on the GST portal
- The buyer has explicitly accepted the invoice on their GST IMS
- The buyer's payment will route through a confirmed channel

This gives lenders confidence that the loan will be repaid (the buyer already confirmed they owe the money), which means better rates for vendors.

## Who uses this platform?

| Role | Who they are | What they do here |
|------|-------------|------------------|
| Vendor/Borrower | Small manufacturer/supplier | Applies for loans against invoices |
| Anchor | Large buyer (auto company, etc.) | Their invoice acceptance powers the loan |
| Lender | NBFC or bank | Receives applications, makes offers |
| Platform operator (us) | Loan Agent + Data Provider | Runs this platform, connects everyone |

## Running the Platform Locally

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) (Python package manager — fast, modern)
- Docker (for local infrastructure like databases)

### Step-by-step

```bash
# 1. Clone the repository
git clone https://github.com/shreyashnadage/project-k-platform.git
cd project-k-platform

# 2. Install all dependencies
uv sync

# 3. Start databases, message broker, and workflow engine
make up

# 4. Verify everything works (should see 71 tests passing)
make test

# 5. Start the API server (borrower gateway)
make gateway
# API is now at http://localhost:8000

# 6. Start the workflow worker (processes loan applications)
make worker
```

### Testing without external services

The platform supports a **sandbox mode** with simulated external services — no need for OCEN credentials, Account Aggregator access, or GST portal connectivity. This is controlled by:

```
INTEGRATION_MODE=sandbox
```

This is a required config — the app will not start without it set to either `sandbox` or `live`. All tests run in sandbox mode and pass without any network access.

## Key Concepts Explained

### Decision Gates (D0-D3)

The platform runs your loan application through a series of checks:

| Gate | What it checks | Who decides |
|------|---------------|-------------|
| D0 | Is the invoice valid? (IRN + IMS + routing) | Platform (us) |
| D1 | Do we have enough financial data? | Platform (us) |
| D2 | What are the derived risk indicators? | Platform (us) |
| D3 | Which lenders match this profile? | Platform (us) |
| D4 | Should we lend? At what rate? | **Lender** (not us) |

We handle D0-D3 (data validation and matching). D4 (the actual credit decision) is always the lender's — that's a regulatory requirement.

### OCEN Network Protocol

When the platform sends a loan application to lenders, it follows OCEN's specific protocol:

1. **Authenticate** — Get a bearer token from OCEN's identity server
2. **Sign** — Digitally sign the request body (so lenders know it's really from us)
3. **Discover** — Look up which lenders are in our product network
4. **Submit** — Send the signed application to each eligible lender
5. **Wait** — Lenders process and respond asynchronously (could take seconds to hours)
6. **Receive** — Lender posts their decision back to our callback endpoints

### Trust Graph (the moat)

Over time, the platform accumulates data that nobody else has:
- Which invoices were attested (confirmed real)
- Which loans were originated against them
- Which loans were repaid on time

This creates a "Trust Graph" — a network of relationships between anchors, vendors, and payment patterns. The more data accumulates, the better the platform gets at matching vendors to lenders, creating a competitive advantage.

## API Endpoints

### For Borrowers (Internal)

| Endpoint | Purpose |
|----------|---------|
| `POST /loans/apply` | Submit a loan application |
| `POST /loans/status` | Check application status |
| `GET /health` | Service health check |

### For Lenders (OCEN Network Callbacks)

All under `/v4.0.0alpha/loanApplications/`:

| Endpoint | When lender calls it |
|----------|---------------------|
| `createLoanResponse` | After evaluating the application |
| `generateOffersResponse` | When they have loan offers ready |
| `setOffersResponse` | Confirming which offer was selected |
| `loanAgreementResponse` | Loan agreement ready for e-sign |
| `grantLoanResponse` | Loan officially granted |
| `triggerDisbursementResponse` | Money has been sent |
| `triggerRepaymentResponse` | Repayment received |
| `setRepaymentPlanResponse` | EMI schedule set |

## Project Layout (What's Where)

```
libs/ocen_client/     → Talks to the OCEN network (authentication, signing, submission)
libs/mocks/           → Fake versions of external services (for testing)
libs/zen_rules/       → Decision engine (evaluates D0-D3 rules)
libs/audit/           → Creates signed records of every decision (for compliance)

services/borrower_gateway/  → The API that borrowers and lenders talk to
services/la_orchestrator/   → The "brain" that runs the loan process step by step
services/vdp_wedge/         → Checks if invoices are real
services/trust_graph/       → Builds the proprietary data advantage
services/ddp_engine/        → Computes derived data for lenders

rules/                → Decision rules in JSON format (editable without code changes)
tests/                → 71 automated tests
```

## Common Tasks

### Add a new decision rule

1. Create a JDM file in `rules/` (e.g., `rules/d3-new-lender-filter.json`)
2. Reference it in the workflow by name
3. Write a test in `tests/`

### Switch from sandbox to live OCEN

1. Set environment variables (OCEN_CLIENT_ID, OCEN_CLIENT_SECRET, etc.)
2. Set `INTEGRATION_MODE=live`
3. Place your RSA keypair at the path specified by `OCEN_KEYPAIR_PATH`

### Run a specific test

```bash
uv run pytest tests/test_ocen_client/test_jws_signer.py -v
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Tests fail with import errors | Run `uv sync` to install dependencies |
| Temporal workflow hangs | Check `make worker` is running |
| "Real OCEN client not yet implemented" | Set `INTEGRATION_MODE=sandbox` |
| Pre-existing event_producer test error | Known issue — Kafka mock limitation, safe to ignore |
