"""Tests for DPDP sandbox scenario loader and DSR client."""

from __future__ import annotations

import pytest

from sandbox.scenarios.loader import ScenarioState, load_scenario, reset_scenario


class TestScenarioLoader:
    def setup_method(self):
        reset_scenario()

    def test_load_consent_denied(self):
        scenario = load_scenario("consent_denied")
        assert scenario is not None
        assert scenario.scenario_id == "consent_denied"
        assert scenario.category == "consent"

    def test_load_erasure_with_legal_hold(self):
        scenario = load_scenario("dsr_erasure_with_legal_hold")
        assert scenario is not None
        assert scenario.expected_outcome["erasure_completed"] is False

    def test_load_nonexistent_returns_none(self):
        scenario = load_scenario("does_not_exist")
        assert scenario is None

    def test_scenario_state_progression(self):
        scenario = load_scenario("consent_denied")
        response = scenario.next_response("consent_check")
        assert response == {"allowed": False, "reason": "consent_not_granted"}

    def test_call_number_routing(self):
        scenario = load_scenario("consent_revoked_mid_flow")
        r1 = scenario.next_response("consent_check")
        assert r1["allowed"] is True
        r2 = scenario.next_response("consent_check")
        assert r2["allowed"] is False
        assert r2["reason"] == "consent_revoked"

    def test_breach_scenario(self):
        scenario = load_scenario("breach_bulk_access_triggered")
        r = scenario.next_response("detect_breaches")
        assert r["confirmed"] is True
        assert r["actual"] == 150

    def test_retention_mixed(self):
        scenario = load_scenario("retention_mixed_categories")
        r = scenario.next_response("enforce_retention")
        assert r["policies_processed"] == 5
        assert len(r["results"]) == 5

    def teardown_method(self):
        reset_scenario()


@pytest.mark.asyncio
class TestSandboxDSRClient:
    async def test_access_default(self):
        reset_scenario()
        from sandbox.clients.dsr_client import SandboxDSRClient

        client = SandboxDSRClient()
        result = await client.execute_access("27AADCB2230M1ZT")
        assert result["status"] == "fulfilled"
        assert result["data"]["vendor"]["gstin"] == "27AADCB2230M1ZT"

    async def test_erasure_default(self):
        reset_scenario()
        from sandbox.clients.dsr_client import SandboxDSRClient

        client = SandboxDSRClient()
        result = await client.execute_erasure("27AADCB2230M1ZT")
        assert result["status"] == "fulfilled"
        assert result["result"]["erased"] is True

    async def test_erasure_with_scenario(self):
        scenario = load_scenario("dsr_erasure_with_legal_hold")
        from sandbox.clients.dsr_client import SandboxDSRClient

        client = SandboxDSRClient()
        result = await client.execute_erasure("27AADCB2230M1ZT")
        assert result["status"] == "held"
        assert result["result"]["erased"] is False
        reset_scenario()
