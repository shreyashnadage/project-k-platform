"""Zen Engine integration tests - load and evaluate the D0 Kind 1 gate."""

from __future__ import annotations

from libs.zen_rules.engine import ZenDecisionEngine


def test_zen_engine_loads_ruleset():
    """ZenDecisionEngine loads the D0 Kind 1 gate ruleset."""
    engine = ZenDecisionEngine("rules/")
    assert "d0-kind1-gate" in engine.loaded_rulesets


def test_zen_engine_ruleset_hash_is_deterministic():
    """The content hash of a ruleset is stable across loads."""
    engine1 = ZenDecisionEngine("rules/")
    engine2 = ZenDecisionEngine("rules/")
    assert engine1.get_ruleset_hash("d0-kind1-gate") == engine2.get_ruleset_hash("d0-kind1-gate")


def test_d0_kind1_pass():
    """All conditions met -> outcome=pass."""
    engine = ZenDecisionEngine("rules/")
    result = engine.evaluate(
        "d0-kind1-gate",
        {
            "irn_valid": True,
            "ims_status": "accepted",
            "repayment_routing_active": True,
            "gstin_valid": True,
        },
    )
    assert result.output["outcome"] == "pass"
    assert result.output["reason"] == "kind1_all_conditions_met"
    assert result.ruleset_hash
    assert result.engine_version == "zen-engine-python"


def test_d0_kind1_flag_deemed_accepted():
    """IMS deemed_accepted -> outcome=flag (weaker signal)."""
    engine = ZenDecisionEngine("rules/")
    result = engine.evaluate(
        "d0-kind1-gate",
        {
            "irn_valid": True,
            "ims_status": "deemed_accepted",
            "repayment_routing_active": True,
            "gstin_valid": True,
        },
    )
    assert result.output["outcome"] == "flag"
    assert result.output["reason"] == "deemed_accepted_weaker_signal"


def test_d0_kind1_fail():
    """Conditions not met -> outcome=fail."""
    engine = ZenDecisionEngine("rules/")
    result = engine.evaluate(
        "d0-kind1-gate",
        {
            "irn_valid": False,
            "ims_status": "rejected",
            "repayment_routing_active": False,
            "gstin_valid": False,
        },
    )
    assert result.output["outcome"] == "fail"
    assert result.output["reason"] == "kind1_conditions_not_met"
