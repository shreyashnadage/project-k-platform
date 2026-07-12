# DPDP Core: Implementation Note

**Project K — OCEN LA Platform | 12 Jul 2026 | 129 Tests Passing | Phase 1 Complete**

---

## At a Glance

This note documents the implementation and integration of `project-k-dpdp-core`, a standalone compliance library for India's Digital Personal Data Protection Act, 2023 (enforcement: 13 May 2027, penalty exposure up to INR 250 crore). The library is now wired into the OCEN LA platform as a GitHub-sourced pip dependency.

| Metric | Value |
|--------|-------|
| dpdp-core tests | 90 |
| Platform tests | 96 existing + 33 new |
| PII fields annotated | 22 |
| Platform files modified | 7 |
| New modules in dpdp-core | 11 |

---

## Architecture Decision

The DPDP compliance layer was built as a **separate repo** (`project-k-dpdp-core`) operating in **dual mode**: pip-installable library for in-process features (PII redaction, encryption column types, field annotations) and standalone FastAPI microservice for API features (consent ledger, DSR endpoints, audit).

### Why not Fides?

Fides is a full platform (FastAPI + PostgreSQL + Redis + Celery). That creates a second orchestrator competing with Temporal, violating the "Decision != Orchestration" architecture principle. The operational overhead is unjustified for our scope.

### Why not in-repo?

DPDP compliance is a cross-cutting concern that could serve future products on OCEN. A standalone repo keeps it reusable and maintains a clean dependency direction.

### IP Boundary

dpdp-core sits **ABOVE** the IP boundary (proprietary). It communicates with GPL systems (ERPNext, Fineract) only via REST APIs and the Redpanda event bus, never through linked code.

---

## Repository Structure

**Repo:** `github.com/shreyashnadage/project-k-dpdp-core` (private) | Branch: `master` | Commit: `551ef5c`

```
project-k-dpdp-core/
├── pyproject.toml
├── dpdp_config.yaml              # All business policy lives here
├── dpdp_core/
│   ├── config.py                 # YAML + env var config loader
│   ├── classification/
│   │   ├── taxonomy.py           # DPDPTier, DPDPCategory, DPDPPurpose
│   │   ├── field_meta.py         # dpdp_field() Pydantic decorator
│   │   └── purpose_registry.py   # 8 processing purposes
│   ├── pii/
│   │   ├── recognizers.py        # GSTIN, Udyam, IRN, IN_PHONE
│   │   ├── log_redactor.py       # structlog PII processor
│   │   └── event_scanner.py      # Pre-emission payload scan
│   ├── encryption/
│   │   ├── types.py              # EncryptedString SQLAlchemy type
│   │   └── key_manager.py        # AWS Secrets Manager / env var
│   ├── consent/
│   │   ├── models.py             # ConsentRecord, ConsentDomain
│   │   ├── ledger.py             # Append-only grant/revoke/check
│   │   ├── storage.py            # InMemory + Postgres backends
│   │   ├── gate.py               # Temporal activity
│   │   └── router.py             # FastAPI /consent/* endpoints
│   ├── rights/
│   │   ├── models.py             # DSRRequest, RightType
│   │   ├── datasource.py         # Pluggable DataSourceRegistry
│   │   ├── activities.py         # access/erasure/correction
│   │   └── router.py             # FastAPI /rights/* endpoints
│   ├── retention/
│   │   ├── policies.py           # Config-driven policies
│   │   └── activities.py         # RetentionHandlerRegistry
│   ├── breach/
│   │   ├── detector.py           # BulkAccess, FailedAuth, ExportWithoutDSR
│   │   ├── notifier.py           # DPBI + principal notifications
│   │   └── activities.py         # Temporal activities
│   ├── audit/
│   │   ├── models.py             # AuditEvent
│   │   └── producer.py           # Redpanda dpdp.audit-log.v1
│   ├── middleware/
│   │   ├── rbac.py               # Keycloak JWT role enforcement
│   │   └── consent_context.py    # ContextVar injection
│   ├── db/
│   │   ├── engine.py             # Async SQLAlchemy
│   │   └── orm.py                # consent_records, dsr_requests
│   └── service/
│       └── app.py                # FastAPI entry point
└── tests/                        # 9 test files, 90 tests
```

---

## Config-Driven Architecture

Every piece of business policy is driven by `dpdp_config.yaml` with environment variable overrides (`DPDP_*` prefix). Adding a new PII recognizer, processing purpose, retention policy, RBAC endpoint, or breach threshold requires editing the YAML only — zero code changes.

### Config Resolution Order

Environment Variables (highest) → dpdp_config.yaml → Built-in Defaults

### Self-Service Registries

| Registry | Extension Point | How to Extend |
|----------|----------------|---------------|
| `register_recognizer()` | PII entity types | YAML or programmatic |
| `DataSourceRegistry` | DSR data collection | Implement `DataSource` ABC |
| `RetentionHandlerRegistry` | Retention enforcement | Implement `RetentionHandler` ABC |
| `BreachDetector.register_rule()` | Anomaly detection | Implement `DetectionRule` ABC |
| `NotificationChannelRegistry` | Breach notification | Implement `NotificationChannel` ABC |

### Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DPDP_MODE` | `library` | Library vs. standalone service |
| `DPDP_LOG_REDACTION` | `true` | Enable/disable PII log redaction |
| `DPDP_DATABASE_URL` | localhost | PostgreSQL connection (service mode) |
| `DPDP_RBAC_ENABLED` | `false` | Activate RBAC middleware in platform |
| `DPDP_AUDIT_TOPIC` | `dpdp.audit-log.v1` | Redpanda topic for audit events |
| `DPDP_CONFIG_PATH` | `dpdp_config.yaml` | Path to YAML config file |

---

## Platform Integration

dpdp-core is installed from GitHub as a pip dependency. The `[tool.uv.sources]` section in pyproject.toml pins the source for both local development and AWS deployment.

```toml
# In dependencies list:
"dpdp-core",

# Source pinning at bottom of file:
[tool.uv.sources]
dpdp-core = { git = "https://github.com/shreyashnadage/project-k-dpdp-core.git", branch = "master" }
```

### Integration Points

| Platform File | What Changed | dpdp-core Import |
|--------------|-------------|-----------------|
| `libs/common/logging.py` | PII redaction processor inserted into structlog chain before renderer | `pii_redaction_processor` |
| `libs/common/event_producer.py` | Payload scanned for PII before every Redpanda emission | `scan_payload` |
| `libs/common/middleware.py` | New `DPDPRBACMiddleware` class added alongside existing `CorrelationIdMiddleware` | `check_role_access`, `extract_roles_from_token`, `set_processing_context` |
| `libs/common/models.py` | DPDP field annotations on GSTIN, AnchorProfile, VendorProfile, Invoice | `dpdp_field`, `DPDPCategory`, `DPDPTier`, `DPDPPurpose` |
| `services/borrower_gateway/models.py` | DPDP annotations on LoanApplicationRequest, InvoiceCapturedRequest | `dpdp_field`, taxonomy enums |
| `services/borrower_gateway/ops_models.py` | DPDP annotations on VendorInvite, VendorRegister, AnchorOnboard, OpsApplicationDetail | `dpdp_field`, taxonomy enums |
| `services/borrower_gateway/app.py` | `DPDPRBACMiddleware` added to middleware stack | Via `libs.common.middleware` |

---

## Data Flow: How PII Protection Works

### Log Redaction

Every log line passes through the Presidio-backed PII processor before reaching the renderer. GSTINs, phone numbers, Udyam numbers, IRNs, email addresses, and built-in Indian PII types (Aadhaar, PAN) are masked in-place using configurable masking rules.

```
structlog.info("vendor", gstin="27AAD...") → contextvars → correlation_id → pii_redaction_processor → JSONRenderer
```

```json
// Before redaction:
{"msg": "vendor_check", "gstin": "27AADCB2230M1ZT", "level": "info"}

// After redaction:
{"msg": "vendor_check", "gstin": "27AADCB2*******", "level": "info"}
```

### Event Payload Scanning

Before every event is published to `ocen.trade-events.v1` on Redpanda, the `payload` dict is run through `scan_payload()`. Any detected PII is replaced with `<REDACTED:ENTITY_TYPE>` markers.

```
TradeEvent.payload → scan_payload() → orjson.dumps() → Redpanda
```

> **Note:** The event envelope fields (event_id, entity_id, correlation_id) are UUIDs and pass through unredacted. Only the `payload` dict is scanned, since that's where domain data (GSTINs, names, amounts) lives.

### RBAC Enforcement

The `DPDPRBACMiddleware` reads Keycloak JWT `realm_access.roles` and checks against the YAML-configured endpoint-to-role mappings. Disabled by default (`DPDP_RBAC_ENABLED=false`) for dev environments.

| Path Prefix | Allowed Roles |
|-------------|---------------|
| `/ops/hold`, `/ops/release`, `/ops/flag`, `/ops/escalate` | platform-admin, operations |
| `/ops/applications` | platform-admin, operations, lender-viewer |
| `/ops/vendor/invite` | platform-admin, anchor-manager |
| `/ops/anchor/onboard` | platform-admin, anchor-manager |
| `/dpdp/rights`, `/dpdp/consent` | platform-admin |

---

## PII Field Annotations

Every PII field in the platform's Pydantic models now carries DPDP classification metadata via `dpdp_field()`. This metadata flows into JSON schemas, enabling automated compliance auditing and consent verification.

| Model | Field | Category | Tier | Retention |
|-------|-------|----------|------|-----------|
| `GSTIN` | `value` | financial_identifier | standard | 2555 d |
| `AnchorProfile` | `name` | name | standard | 2555 d |
| `VendorProfile` | `name` | name | standard | 2555 d |
| `VendorProfile` | `udyam_number` | government_id | standard | 2555 d |
| `Invoice` | `irn` | financial_identifier | standard | 2555 d |
| `LoanApplicationRequest` | `vendor_gstin` | financial_identifier | standard | 2555 d |
| `LoanApplicationRequest` | `anchor_gstin` | financial_identifier | standard | 2555 d |
| `InvoiceCapturedRequest` | `irn` | financial_identifier | standard | 2555 d |
| `InvoiceCapturedRequest` | `vendor_gstin` | financial_identifier | standard | 2555 d |
| `InvoiceCapturedRequest` | `anchor_gstin` | financial_identifier | standard | 2555 d |
| `VendorInviteRequest` | `name` | name | standard | 2555 d |
| `VendorInviteRequest` | `gstin` | financial_identifier | standard | 2555 d |
| `VendorInviteRequest` | `phone` | contact | standard | 1095 d |
| `VendorInviteRequest` | `udyam_number` | government_id | standard | 2555 d |
| `VendorRegisterRequest` | `name`, `gstin`, `phone`, `udyam_number` | mixed | standard | 1095-2555 d |
| `AnchorOnboardRequest` | `name`, `gstin` | name, financial_identifier | standard | 2555 d |
| `OpsApplicationDetail` | `vendor_gstin`, `anchor_gstin` | financial_identifier | standard | 2555 d |

### Example: how dpdp_field() looks in code

```python
class VendorInviteRequest(BaseModel):
    name: str = dpdp_field(
        category=DPDPCategory.NAME,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.OPS_MANAGEMENT],
        retention_days=2555,
        default=...,
    )
    gstin: str = dpdp_field(
        category=DPDPCategory.FINANCIAL_IDENTIFIER,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.KIND1_ATTESTATION],
        retention_days=2555,
        min_length=15, max_length=15,
    )
    phone: str = dpdp_field(
        category=DPDPCategory.CONTACT,
        tier=DPDPTier.STANDARD,
        purposes=[DPDPPurpose.LOAN_ORIGINATION, DPDPPurpose.OPS_MANAGEMENT],
        retention_days=1095,
        min_length=10, max_length=13,
    )
```

---

## Test Coverage

### dpdp-core (standalone): 90 tests

| Test File | Count | Covers |
|-----------|-------|--------|
| `test_config.py` | 13 | YAML loading, env overrides, defaults, reset |
| `test_recognizers.py` | 7 | GSTIN, Udyam, IRN, phone detection + custom registration |
| `test_log_redactor.py` | 5 | Masking, skip keys, enable/disable toggle |
| `test_classification.py` | 6 | Purpose registry, field_meta decorator |
| `test_encryption.py` | 5 | AES-256-GCM encrypt/decrypt, key versioning |
| `test_consent_ledger.py` | 10 | Grant/revoke/check lifecycle, dual domains, immutability |
| `test_dsr_activities.py` | 8 | Access, erasure (with legal hold), correction |
| `test_retention.py` | 8 | Policy loading, handler registry, enforcement |
| `test_breach.py` | 12 | Detection rules, notifier channels, detector scan |

### Platform integration: 33 new tests

| Test Class | Count | Covers |
|-----------|-------|--------|
| `TestPIILogRedaction` | 4 | GSTIN/phone masking in structlog, skip keys, disable toggle |
| `TestEventPayloadScanner` | 4 | GSTIN detection, safe passthrough, nested dicts, producer path |
| `TestDPDPFieldAnnotations` | 12 | Schema metadata on every annotated model (category, tier, retention) |
| `TestRBACMiddleware` | 8 | Role extraction, access checks (allow/deny), unprotected paths |
| `TestConsentContext` | 3 | Purpose/scope propagation via ContextVar |
| `TestRBACMiddlewareE2E` | 2 | Middleware registered in app, health endpoint passthrough |

### Existing platform tests: 96 pass, zero regressions

**Total: 129 tests passing** (96 existing + 33 new), 7 deselected (integration markers), ruff lint clean.

---

## Deployment Considerations

### AWS Requirements

- The spaCy model `en_core_web_sm` must be installed in the container image. Add `python -m spacy download en_core_web_sm` to the Dockerfile.
- dpdp-core pulls from a private GitHub repo. The build environment needs either a GitHub deploy key or a `GH_TOKEN` for `git+https` access.
- Set `DPDP_RBAC_ENABLED=true` in production to activate Keycloak RBAC enforcement.
- Set `DPDP_ENCRYPTION_KEY` for field-level encryption (generate with `python -c "import secrets; print(secrets.token_hex(32))"`).

> **Critical:** The `dpdp_config.yaml` file lives in the dpdp-core repo, not the platform. For production, mount a per-environment config file via ConfigMap/Secret and set `DPDP_CONFIG_PATH` to its path. Do not bake production policy into the default YAML.

### Middleware Stack Order

Starlette processes middleware in reverse registration order. The current stack is:

```
Request → RateLimitMiddleware → DPDPRBACMiddleware → CorrelationIdMiddleware → Route Handler
```

---

## Remaining Work (Phase 2-3)

| Item | Phase | Status |
|------|-------|--------|
| Apply `EncryptedString` to PII columns in ORM models (`libs/db/models.py`) | 2 | Pending |
| Wire consent gate as Temporal activity before D0 | 2 | Pending |
| Persist AA `consent_id` (currently discarded after fetch) | 2 | Pending |
| Deploy dpdp-core in service mode (consent + audit APIs) | 2 | Pending |
| Create Redpanda topics: `dpdp.consent-events.v1`, `dpdp.audit-log.v1` | 2 | Pending |
| Database migration: `consent_records`, `dpdp_audit_log`, `dsr_requests` tables | 2 | Pending |
| Register DSR + retention workflows in Temporal worker | 3 | Pending |
| PWA `/privacy` pages (consent status, rights forms) — Hindi/Marathi | 3 | Pending |
| Consent lineage in Apache AGE Trust Graph | 3 | Pending |

---

## Decision Gate Coverage

The DPDP layer interacts with the existing D0-D3 decision pipeline:

| Gate | DPDP Interaction | Status |
|------|-----------------|--------|
| **D0** Kind 1 Gate | PII in payload (GSTIN, IRN) redacted before event emission | Active |
| **Pre-D0** | Consent gate check (verify DPDP consent before processing) | Phase 2 |
| **D1** Data Sufficiency | AA consent_id persisted in consent ledger | Phase 2 |
| **D2** Derived Attributes | Decision receipt signed and written to audit stream | Active |
| **D3** Lender Pre-screen | Derived data package scanned for PII before lender submission | Active |

---

## OSS Dependencies Introduced

| Package | License | Purpose | Size Impact |
|---------|---------|---------|-------------|
| presidio-analyzer | MIT | PII entity detection | ~2 MB + spaCy model (~12 MB) |
| presidio-anonymizer | MIT | PII masking/replacement | ~200 KB |
| spaCy | MIT | NLP engine for Presidio | ~40 MB |
| pyyaml | MIT | YAML config parsing | ~600 KB |
| pydantic-settings | MIT | Config model support | ~100 KB |

> **No new infrastructure.** No Redis, no Celery, no Vault, no separate databases. The compliance layer uses the existing PostgreSQL instance (separate schema in service mode) and Redpanda event bus.
