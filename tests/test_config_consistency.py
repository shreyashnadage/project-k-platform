"""Architect-perspective tests: config and code can't silently drift apart.

Each test here would have caught a real drift bug found during audit:
- DDP engine's D2 risk-flag thresholds vs rules/d2-derived-flags.json
- dpdp_field(retention_days=...) literals vs dpdp_config.yaml's retention list
- Security-critical env vars silently falling back to known dev defaults
  outside sandbox mode
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_import_in_subprocess(module: str, env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("INTEGRATION_MODE", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestD2ThresholdConsistency:
    """The DDP engine (external /ddp/compute API) and the Temporal workflow's
    D2 gate must evaluate the exact same rules/d2-derived-flags.json —
    boundary values on each side of every threshold prove they agree."""

    def test_concentration_boundary_matches_jdm_threshold(self):
        from decimal import Decimal

        from services.ddp_engine.service import DDPEngineService

        svc = DDPEngineService()
        attrs = svc._compute_attributes(_fake_request(invoice_amount=Decimal("1")))

        attrs.revenue_concentration = Decimal("80")  # exactly at the JDM's "> 0.8" boundary
        flags_at_boundary = svc._evaluate_risk_flags(attrs)
        assert not any(f.flag_code == "HIGH_CONCENTRATION" for f in flags_at_boundary), (
            "80% concentration should NOT trigger HIGH_CONCENTRATION — "
            "rules/d2-derived-flags.json uses a strict '> 0.8', not '>='"
        )

        attrs.revenue_concentration = Decimal("81")
        flags_over = svc._evaluate_risk_flags(attrs)
        assert any(f.flag_code == "HIGH_CONCENTRATION" for f in flags_over), (
            "81% concentration should trigger HIGH_CONCENTRATION per "
            "rules/d2-derived-flags.json's '> 0.8' rule"
        )

    def test_dso_boundary_matches_jdm_threshold(self):
        from decimal import Decimal

        from services.ddp_engine.service import DDPEngineService

        svc = DDPEngineService()
        attrs = svc._compute_attributes(_fake_request(invoice_amount=Decimal("1")))

        attrs.dso_days = 90
        assert not any(f.flag_code == "HIGH_DSO" for f in svc._evaluate_risk_flags(attrs))

        attrs.dso_days = 91
        assert any(f.flag_code == "HIGH_DSO" for f in svc._evaluate_risk_flags(attrs))

    def test_ruleset_hash_is_real_content_hash_not_placeholder(self):
        from services.ddp_engine.service import DDPEngineService

        svc = DDPEngineService()
        assert svc._ruleset_hash != "ddp-derived-v1-placeholder"
        assert len(svc._ruleset_hash) == 64  # SHA-256 hex digest


def _fake_request(invoice_amount):
    from uuid import uuid4

    from services.ddp_engine.models import DerivedDataRequest

    return DerivedDataRequest(
        loan_application_id=uuid4(),
        vendor_gstin="27AADCB2230M1ZT",
        anchor_gstin="27AABCU9603R1ZM",
        invoice_amount=invoice_amount,
        gst_returns_months=12,
    )


class TestMigrationChainConsistency:
    """The alembic revision graph in migrations/versions/ must form a single
    unbroken chain with exactly one head. This would have caught the real
    004/005 break: 005 originally chained after 004, but 004 drops columns
    (vendor/anchor plaintext gstin/name) that libs/db/models.py and
    libs/db/data_source.py still directly query — 004 was never actually
    runnable, and nothing chained past both 004 and 005, producing two
    divergent heads. 004 now lives in migrations/deferred/, out of the
    active graph; this test guards against a future migration accidentally
    re-introducing a fork."""

    def test_versions_directory_has_exactly_one_head(self):
        import ast

        versions_dir = os.path.join(REPO_ROOT, "migrations", "versions")
        revisions: dict[str, str | None] = {}
        for fname in os.listdir(versions_dir):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            path = os.path.join(versions_dir, fname)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fname)
            values: dict[str, str | None] = {}
            for node in tree.body:
                if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                    continue
                if node.target.id not in ("revision", "down_revision"):
                    continue
                if isinstance(node.value, ast.Constant):
                    values[node.target.id] = node.value.value
            assert "revision" in values, f"{fname} has no `revision` assignment"
            revisions[values["revision"]] = values.get("down_revision")

        down_revisions = set(revisions.values())
        heads = [rev for rev in revisions if rev not in down_revisions]
        assert len(heads) == 1, (
            f"Expected exactly one alembic head in migrations/versions/, found "
            f"{heads}. Multiple heads mean two migrations both claim to be the "
            f"latest — alembic upgrade head will fail or pick one ambiguously."
        )

    def test_migration_004_is_not_in_the_active_chain(self):
        versions_dir = os.path.join(REPO_ROOT, "migrations", "versions")
        assert "004_drop_plaintext_columns.py" not in os.listdir(versions_dir), (
            "Migration 004 drops columns libs/db/models.py still queries directly "
            "(see migrations/deferred/README.md) — it must not be reintroduced to "
            "migrations/versions/ without also updating the ORM models and every "
            "call site in the same change."
        )


class TestGateOutputNormalization:
    """D0/D1 rulesets use hitPolicy "first" -> EvaluationResult.output is a
    dict. D2/D3 use "collect" with multiple named outputs -> output is a
    list[dict] (one row per matched rule). evaluate_decision's activity code
    used to call dict-only methods (.get()) directly on result.output
    regardless of shape — broken for D2/D3 specifically. This locks in the
    fix (_normalize_rule_output) so it can't silently regress."""

    def test_d0_and_d1_rulesets_produce_dict_output(self):
        from libs.zen_rules.engine import ZenDecisionEngine

        engine = ZenDecisionEngine("rules/")
        d0 = engine.evaluate(
            "d0-kind1-gate",
            {
                "irn_valid": True,
                "ims_status": "accepted",
                "repayment_routing_active": True,
                "gstin_valid": True,
            },
        )
        assert isinstance(d0.output, dict)

        d1 = engine.evaluate(
            "d1-data-sufficiency",
            {"months_available": 12, "data_freshness_days": 5, "gst_returns_filed": True},
        )
        assert isinstance(d1.output, dict)

    def test_d2_and_d3_rulesets_produce_list_output(self):
        from libs.zen_rules.engine import ZenDecisionEngine

        engine = ZenDecisionEngine("rules/")
        d2 = engine.evaluate(
            "d2-derived-flags",
            {
                "revenue_concentration": 0.5,
                "days_sales_outstanding": 30,
                "dilution_rate": 0.05,
                "anchor_avg_dpd": 5,
                "gst_compliance_score": 90.0,
                "vintage_months": 12,
            },
        )
        assert isinstance(d2.output, list)

        d3_no_match = engine.evaluate(
            "d3-lender-prescreen",
            {
                "risk_flag_count": 99,
                "requested_amount": 999999999,
                "months_of_data": 0,
                "trust_score": 0,
            },
        )
        assert d3_no_match.output == []

        d3_match = engine.evaluate(
            "d3-lender-prescreen",
            {
                "risk_flag_count": 0,
                "requested_amount": 100000,
                "months_of_data": 12,
                "trust_score": 80,
            },
        )
        assert isinstance(d3_match.output, list)
        assert all("matched_lender_id" in row for row in d3_match.output)

    def test_normalize_rule_output_handles_dict_passthrough(self):
        from services.la_orchestrator.activities import _normalize_rule_output

        raw = {"outcome": "pass", "reason": "kind1_all_conditions_met"}
        assert _normalize_rule_output("d0-kind1-gate", raw) == raw

    def test_normalize_rule_output_extracts_matched_lenders_from_d3_list(self):
        from services.la_orchestrator.activities import _normalize_rule_output

        rows = [
            {"matched_lender_id": "lender-conservative-01", "priority": 1},
            {"matched_lender_id": "lender-standard-01", "priority": 2},
        ]
        normalized = _normalize_rule_output("d3-lender-prescreen", rows)
        assert normalized["outcome"] == "pass"
        assert normalized["matched_lender_ids"] == [
            "lender-conservative-01",
            "lender-standard-01",
        ]

    def test_normalize_rule_output_fails_d3_with_no_matches(self):
        from services.la_orchestrator.activities import _normalize_rule_output

        normalized = _normalize_rule_output("d3-lender-prescreen", [])
        assert normalized["outcome"] == "fail"
        assert normalized["matched_lender_ids"] == []

    def test_normalize_rule_output_d2_flags_are_informational_only(self):
        from services.la_orchestrator.activities import _normalize_rule_output

        rows = [{"flag": "high_concentration", "severity": "high"}]
        normalized = _normalize_rule_output("d2-derived-flags", rows)
        assert normalized["outcome"] == "pass", "D2 flags must never block the workflow"

    @pytest.mark.asyncio
    async def test_evaluate_decision_does_not_crash_on_d3_list_output(self):
        """Regression test for the AttributeError this fix addresses:
        result.output.get(...) on a list raises 'list' object has no
        attribute 'get'. This is the exact D3 context shape that used to
        break — asserts evaluate_decision returns real matched_lender_ids,
        not the silently-always-empty list from before."""
        from services.la_orchestrator.activities import EvaluateDecisionInput, evaluate_decision

        result = await evaluate_decision(
            EvaluateDecisionInput(
                loan_application_id=str(__import__("uuid").uuid4()),
                gate="d3_lender_prescreen",
                ruleset_name="d3-lender-prescreen",
                context={
                    "risk_flag_count": 0,
                    "requested_amount": 100000,
                    "months_of_data": 12,
                    "trust_score": 80,
                },
            )
        )
        assert result["outcome"] == "pass"
        assert result["matched_lender_ids"], (
            "matched_lender_ids must be populated when the D3 ruleset matches "
            "lenders — previously always empty due to a key-name mismatch "
            "('matched_lender_ids' vs the ruleset's 'matched_lender_id') "
            "compounded by a list-vs-dict AttributeError"
        )


class TestRetentionConfigConsistency:
    """Every dpdp_field(retention_days=...) call must resolve to a value
    that's actually present in dpdp_config.yaml's retention list — not
    just present (existing test), but numerically correct."""

    def test_retention_constants_match_dpdp_config_yaml(self):
        import yaml

        from libs.common.models import RETENTION_LOAN_APPLICATION, RETENTION_VENDOR_CONTACT

        with open(os.path.join(REPO_ROOT, "dpdp_config.yaml")) as f:
            raw = yaml.safe_load(f)

        by_category = {p["data_category"]: p["retention_days"] for p in raw["retention"]}
        assert by_category["loan_application"] == RETENTION_LOAN_APPLICATION
        assert by_category["vendor_contact"] == RETENTION_VENDOR_CONTACT

    def test_annotated_model_fields_use_the_shared_constants(self):
        from libs.common.models import (
            GSTIN,
            RETENTION_LOAN_APPLICATION,
            AnchorProfile,
            VendorProfile,
        )

        for model in (GSTIN, AnchorProfile, VendorProfile):
            schema = model.model_json_schema()
            for field_name, props in schema["properties"].items():
                if "dpdp_category" in props:
                    assert props["dpdp_retention_days"] == RETENTION_LOAN_APPLICATION, (
                        f"{model.__name__}.{field_name} retention_days doesn't match "
                        "the shared RETENTION_LOAN_APPLICATION constant"
                    )

    def test_legal_hold_check_uses_same_retention_source_as_enforcement(self):
        """libs/db/data_source.py::has_legal_hold and
        services/la_orchestrator/activities.py::enforce_retention must read
        the same dpdp_config.yaml value — this test would have caught the
        original hardcoded-2555-vs-config drift."""
        import inspect

        from libs.db.data_source import PlatformDataSource

        source = inspect.getsource(PlatformDataSource.has_legal_hold)
        assert "2555" not in source, "has_legal_hold must not hardcode a retention day count"
        assert "get_config" in source, "has_legal_hold must read dpdp_config.yaml at call time"


class TestSecurityDefaultsFailFast:
    """Every credential/URL that has a known dev-only default must refuse
    to start with that default outside INTEGRATION_MODE=sandbox."""

    def test_ops_api_key_fails_fast_outside_sandbox(self):
        env = {"DPDP_RBAC_ENABLED": "false"}
        env.pop("OPS_API_KEY", None)
        result = _run_import_in_subprocess("services.borrower_gateway.ops_api", env)
        assert result.returncode != 0
        assert "OPS_API_KEY" in result.stderr

    def test_ops_api_key_starts_fine_in_sandbox(self):
        result = _run_import_in_subprocess(
            "services.borrower_gateway.ops_api", {"INTEGRATION_MODE": "sandbox"}
        )
        assert result.returncode == 0

    def test_backoffice_webhook_secret_fails_fast_outside_sandbox(self):
        result = _run_import_in_subprocess("services.backoffice_sync.config", {})
        assert result.returncode != 0
        assert "BACKOFFICE_WEBHOOK_SECRET" in result.stderr

    def test_backoffice_webhook_secret_starts_fine_in_sandbox(self):
        result = _run_import_in_subprocess(
            "services.backoffice_sync.config", {"INTEGRATION_MODE": "sandbox"}
        )
        assert result.returncode == 0

    def test_database_url_fails_fast_outside_sandbox(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        env.pop("INTEGRATION_MODE", None)
        result = subprocess.run(
            [sys.executable, "-c", "import libs.db.engine"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "DATABASE_URL" in result.stderr

    def test_database_url_starts_fine_in_sandbox(self):
        result = _run_import_in_subprocess("libs.db.engine", {"INTEGRATION_MODE": "sandbox"})
        assert result.returncode == 0

    def test_ocen_network_client_fails_fast_on_dev_defaults_outside_sandbox(self):
        env = dict(os.environ)
        env.pop("INTEGRATION_MODE", None)
        for var in ("OCEN_TOKEN_URL", "OCEN_REGISTRY_BASE_URL", "OCEN_HEARTBEAT_URL"):
            env.pop(var, None)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from libs.ocen_client.network_client import OcenNetworkClient as C; C()",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "dev network" in result.stderr

    def test_ocen_network_client_starts_fine_in_sandbox(self):
        env = dict(os.environ)
        env["INTEGRATION_MODE"] = "sandbox"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from libs.ocen_client.network_client import OcenNetworkClient as C; C()",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
