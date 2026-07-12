"""Scenario loader for DPDP sandbox testing.

Loads scenario definitions from registry.yaml and provides step-by-step
response mocking driven by DPDP_SANDBOX_SCENARIO environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class ScenarioState:
    """Tracks progression through a scenario's steps."""

    def __init__(self, scenario: dict) -> None:
        self.scenario_id = scenario["id"]
        self.description = scenario["description"]
        self.category = scenario["category"]
        self.steps = scenario.get("steps", [])
        self.expected_outcome = scenario.get("expected_outcome")
        self._step_index = 0
        self._call_counts: dict[str, int] = {}

    def next_response(self, action: str) -> dict[str, Any] | None:
        """Get the next response for a given action, advancing state."""
        self._call_counts[action] = self._call_counts.get(action, 0) + 1
        call_number = self._call_counts[action]

        for step in self.steps:
            if step["action"] != action:
                continue
            step_call = step.get("call_number")
            if step_call is not None and step_call != call_number:
                continue
            return step.get("response")

        return None

    @property
    def is_complete(self) -> bool:
        total_calls = sum(self._call_counts.values())
        return total_calls >= len(self.steps)


_active_scenario: ScenarioState | None = None


def load_scenario(scenario_id: str | None = None) -> ScenarioState | None:
    """Load a scenario by ID from the registry."""
    global _active_scenario

    if scenario_id is None:
        scenario_id = os.environ.get("DPDP_SANDBOX_SCENARIO", "")

    if not scenario_id:
        return None

    registry_path = Path(__file__).parent / "registry.yaml"
    if not registry_path.exists():
        return None

    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    for scenario in registry.get("scenarios", []):
        if scenario["id"] == scenario_id:
            _active_scenario = ScenarioState(scenario)
            return _active_scenario

    return None


def get_active_scenario() -> ScenarioState | None:
    """Get the currently active scenario (loaded or from env)."""
    global _active_scenario
    if _active_scenario is None:
        load_scenario()
    return _active_scenario


def reset_scenario() -> None:
    """Reset the active scenario (for testing)."""
    global _active_scenario
    _active_scenario = None
