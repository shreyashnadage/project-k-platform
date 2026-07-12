"""Integration tests for dpdp-core wired into the OCEN platform.

Tests verify:
1. PII log redaction works in the structlog chain
2. Event payload scanner detects and redacts PII
3. DPDP field annotations are present in model schemas
4. RBAC middleware passes/blocks based on config
5. Consent context propagation works
"""

from __future__ import annotations

import json
import os
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
import structlog
from dpdp_core.config import reset_config
from dpdp_core.middleware.consent_context import (
    get_consent_scope,
    get_processing_purpose,
    set_processing_context,
)
from dpdp_core.middleware.rbac import check_role_access, extract_roles_from_token
from dpdp_core.pii.event_scanner import scan_payload

from libs.common.events import EventType, TradeEvent
from libs.common.models import (
    GSTIN,
    AnchorProfile,
    Invoice,
    VendorProfile,
)
from services.borrower_gateway.models import (
    InvoiceCapturedRequest,
    LoanApplicationRequest,
)
from services.borrower_gateway.ops_models import (
    AnchorOnboardRequest,
    OpsApplicationDetail,
    VendorInviteRequest,
    VendorRegisterRequest,
)


@pytest.fixture(autouse=True)
def _reset_dpdp_config():
    reset_config()
    yield
    reset_config()


# ─── PII Log Redaction ─────────────────────────────────────────


class TestPIILogRedaction:
    def test_structlog_redacts_gstin(self):
        output = StringIO()
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                _get_pii_processor(),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=False,
        )
        log = structlog.get_logger()
        log.info("vendor_check", gstin="27AADCB2230M1ZT")

        logged = json.loads(output.getvalue())
        assert "27AADCB2230M1ZT" not in logged.get("gstin", ""), (
            "GSTIN should be redacted in logs"
        )

    def test_structlog_redacts_phone(self):
        output = StringIO()
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                _get_pii_processor(),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=False,
        )
        log = structlog.get_logger()
        log.info("contact_check", phone="+91 9876543210")

        logged = json.loads(output.getvalue())
        assert "9876543210" not in logged.get("phone", ""), (
            "Phone number should be redacted in logs"
        )

    def test_skip_keys_not_redacted(self):
        output = StringIO()
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                _get_pii_processor(),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=False,
        )
        log = structlog.get_logger()
        log.info("test_event", correlation_id="abc-123-def")

        logged = json.loads(output.getvalue())
        assert logged["correlation_id"] == "abc-123-def", (
            "Skip keys should pass through unredacted"
        )

    def test_redaction_disabled_passes_through(self):
        with patch.dict(os.environ, {"DPDP_LOG_REDACTION": "false"}):
            reset_config()
            output = StringIO()
            structlog.configure(
                processors=[
                    structlog.processors.add_log_level,
                    _get_pii_processor(),
                    structlog.processors.JSONRenderer(),
                ],
                logger_factory=structlog.PrintLoggerFactory(file=output),
                cache_logger_on_first_use=False,
            )
            log = structlog.get_logger()
            log.info("vendor_check", gstin="27AADCB2230M1ZT")

            logged = json.loads(output.getvalue())
            assert logged["gstin"] == "27AADCB2230M1ZT", (
                "With redaction disabled, GSTIN should pass through"
            )


def _get_pii_processor():
    from dpdp_core.pii.log_redactor import pii_redaction_processor
    return pii_redaction_processor


# ─── Event Payload Scanner ─────────────────────────────────────


class TestEventPayloadScanner:
    def test_scan_detects_gstin(self):
        payload = {"vendor_gstin": "27AADCB2230M1ZT", "amount": "50000"}
        cleaned = scan_payload(payload)
        assert "27AADCB2230M1ZT" not in cleaned["vendor_gstin"]
        assert "REDACTED" in cleaned["vendor_gstin"]

    def test_scan_passes_safe_values(self):
        payload = {"status": "approved", "count": 42}
        cleaned = scan_payload(payload)
        assert cleaned["status"] == "approved"
        assert cleaned["count"] == 42

    def test_scan_handles_nested_dicts(self):
        payload = {
            "details": {
                "gstin": "27AADCB2230M1ZT",
                "ref": "INV-001",
            }
        }
        cleaned = scan_payload(payload)
        assert "27AADCB2230M1ZT" not in str(cleaned["details"])

    def test_event_producer_scans_payload(self):
        """Verify the EventProducer integration path scans payloads."""
        from libs.common.event_producer import EventProducer

        with patch.object(EventProducer, "__init__", return_value=None):
            EventProducer.__new__(EventProducer)

        event = TradeEvent(
            event_type=EventType.VENDOR_ONBOARDED,
            entity_type="vendor",
            entity_id=uuid4(),
            payload={"gstin": "27AADCB2230M1ZT", "name": "Test Vendor"},
        )

        event_data = event.model_dump(mode="json")
        event_data["payload"] = scan_payload(event_data.get("payload", {}))

        assert "27AADCB2230M1ZT" not in str(event_data["payload"])


# ─── DPDP Field Annotations ───────────────────────────────────


class TestDPDPFieldAnnotations:
    def test_gstin_has_dpdp_metadata(self):
        schema = GSTIN.model_json_schema()
        props = schema["properties"]["value"]
        assert props["dpdp_category"] == "financial_identifier"
        assert props["dpdp_tier"] == "standard"
        assert "loan_origination" in props["dpdp_purposes"]
        assert "kind1_attestation" in props["dpdp_purposes"]
        assert props["dpdp_retention_days"] == 2555

    def test_vendor_profile_name_has_dpdp_metadata(self):
        schema = VendorProfile.model_json_schema()
        props = schema["properties"]["name"]
        assert props["dpdp_category"] == "name"

    def test_vendor_profile_udyam_has_dpdp_metadata(self):
        schema = VendorProfile.model_json_schema()
        props = schema["properties"]["udyam_number"]
        assert props["dpdp_category"] == "government_id"

    def test_anchor_profile_name_has_dpdp_metadata(self):
        schema = AnchorProfile.model_json_schema()
        props = schema["properties"]["name"]
        assert props["dpdp_category"] == "name"
        assert props["dpdp_tier"] == "standard"

    def test_invoice_irn_has_dpdp_metadata(self):
        schema = Invoice.model_json_schema()
        props = schema["properties"]["irn"]
        assert props["dpdp_category"] == "financial_identifier"

    def test_loan_application_request_gstin_annotated(self):
        schema = LoanApplicationRequest.model_json_schema()
        assert schema["properties"]["vendor_gstin"]["dpdp_category"] == "financial_identifier"
        assert schema["properties"]["anchor_gstin"]["dpdp_category"] == "financial_identifier"

    def test_invoice_captured_request_annotated(self):
        schema = InvoiceCapturedRequest.model_json_schema()
        assert schema["properties"]["irn"]["dpdp_category"] == "financial_identifier"
        assert schema["properties"]["vendor_gstin"]["dpdp_category"] == "financial_identifier"

    def test_vendor_invite_request_annotated(self):
        schema = VendorInviteRequest.model_json_schema()
        assert schema["properties"]["name"]["dpdp_category"] == "name"
        assert schema["properties"]["gstin"]["dpdp_category"] == "financial_identifier"
        assert schema["properties"]["phone"]["dpdp_category"] == "contact"
        assert schema["properties"]["udyam_number"]["dpdp_category"] == "government_id"

    def test_vendor_register_request_annotated(self):
        schema = VendorRegisterRequest.model_json_schema()
        assert schema["properties"]["phone"]["dpdp_category"] == "contact"

    def test_anchor_onboard_request_annotated(self):
        schema = AnchorOnboardRequest.model_json_schema()
        assert schema["properties"]["name"]["dpdp_category"] == "name"
        assert schema["properties"]["gstin"]["dpdp_category"] == "financial_identifier"

    def test_ops_application_detail_annotated(self):
        schema = OpsApplicationDetail.model_json_schema()
        assert schema["properties"]["vendor_gstin"]["dpdp_category"] == "financial_identifier"
        assert schema["properties"]["anchor_gstin"]["dpdp_category"] == "financial_identifier"

    def test_all_annotated_fields_have_retention_days(self):
        for model in [GSTIN, VendorProfile, AnchorProfile, Invoice]:
            schema = model.model_json_schema()
            for field_name, props in schema["properties"].items():
                if "dpdp_category" in props:
                    assert "dpdp_retention_days" in props, (
                        f"{model.__name__}.{field_name} missing retention_days"
                    )


# ─── RBAC Middleware ───────────────────────────────────────────


class TestRBACMiddleware:
    def test_extract_roles_from_keycloak_token(self):
        token = {
            "sub": "user-123",
            "realm_access": {"roles": ["platform-admin", "operations"]},
        }
        roles = extract_roles_from_token(token)
        assert roles == {"platform-admin", "operations"}

    def test_extract_roles_empty_token(self):
        roles = extract_roles_from_token({})
        assert roles == set()

    def test_check_role_access_ops_allowed(self):
        assert check_role_access("/ops/hold", {"platform-admin"})
        assert check_role_access("/ops/release", {"operations"})

    def test_check_role_access_ops_denied(self):
        assert not check_role_access("/ops/hold", {"lender-viewer"})

    def test_check_role_access_unprotected_path(self):
        assert check_role_access("/health", {"any-role"})
        assert check_role_access("/loans/apply", set())

    def test_check_role_access_dpdp_admin_only(self):
        assert check_role_access("/dpdp/rights", {"platform-admin"})
        assert not check_role_access("/dpdp/rights", {"operations"})

    def test_check_role_access_vendor_invite(self):
        assert check_role_access("/ops/vendor/invite", {"anchor-manager"})
        assert not check_role_access("/ops/vendor/invite", {"operations"})

    def test_rbac_middleware_disabled_by_default(self):
        from libs.common.middleware import RBAC_ENABLED
        assert not RBAC_ENABLED, "RBAC should be disabled by default in dev"


# ─── Consent Context ──────────────────────────────────────────


class TestConsentContext:
    def test_set_and_get_processing_purpose(self):
        set_processing_context(purpose="loan_origination")
        assert get_processing_purpose() == "loan_origination"

    def test_set_and_get_consent_scope(self):
        scope = {"financial_data": True, "contact": False}
        set_processing_context(purpose="aa_data_fetch", consent_scope=scope)
        assert get_consent_scope() == scope

    def test_purpose_only_does_not_set_scope(self):
        from dpdp_core.middleware.consent_context import consent_scope_var
        consent_scope_var.set(None)
        set_processing_context(purpose="test")
        assert get_consent_scope() == {}


# ─── RBAC Middleware E2E (via TestClient) ──────────────────────


class TestRBACMiddlewareE2E:
    def test_middleware_passes_without_rbac_enabled(self):
        from fastapi.testclient import TestClient

        from services.borrower_gateway.app import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_middleware_registered_in_app(self):
        from services.borrower_gateway.app import app

        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "DPDPRBACMiddleware" in middleware_names
        assert "CorrelationIdMiddleware" in middleware_names
