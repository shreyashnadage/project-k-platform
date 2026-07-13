"""GoRules Zen Engine wrapper with content-addressed ruleset loading.

The Zen Engine runs IN-PROCESS via Python bindings (Rust core, MIT licence).
No separate JVM service, no network hop.

Rulesets are JSON Decision Model (JDM) files stored in rules/ and
identified by their SHA-256 content hash — the hash IS the version.

Usage:
    engine = ZenDecisionEngine("rules/")
    result = engine.evaluate("d0-kind1-gate", {"irn_valid": True, ...})
    # result.output, result.ruleset_hash, result.engine_version
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvaluationResult:
    """Result of a rule evaluation, ready for receipt creation.

    `output`'s shape depends on the ruleset's hit policy: "first"/"collect"
    with a single output field yields a dict; "collect" with multiple named
    output fields yields a list of per-matched-row dicts (verified against
    the actual GoRules zen-engine Python bindings, not assumed) — e.g.
    rules/d2-derived-flags.json and rules/d3-lender-prescreen.json both
    return list[dict] since each has multiple named outputs.
    """

    output: dict[str, Any] | list[dict[str, Any]]
    ruleset_hash: str
    engine_version: str
    ruleset_name: str


class ZenDecisionEngine:
    """Wraps the GoRules Zen Engine Python bindings.

    Loads JDM ruleset files from a directory, content-addresses them,
    and evaluates inputs against them. Thread-safe (Rust engine is safe).

    Args:
        rules_dir: Path to the directory containing .json JDM files.
    """

    def __init__(self, rules_dir: str | Path) -> None:
        self._rules_dir = Path(rules_dir)
        self._engines: dict[str, Any] = {}  # name → ZenEngine instance
        self._hashes: dict[str, str] = {}  # name → SHA-256 hash
        self._engine_version: str = ""
        self._load_all()

    def _load_all(self) -> None:
        """Load all .json rulesets from the rules directory."""
        try:
            from zen import ZenDecisionContent, ZenEngine

            self._engine_version = "zen-engine-python"
            self._zen_content_cls = ZenDecisionContent
        except ImportError:
            # Graceful degradation for environments without the Rust bindings
            import warnings

            warnings.warn(
                "zen-engine not installed. Using stub engine. Install with: pip install zen-engine",
                stacklevel=2,
            )
            self._engine_version = "stub-0.0.0"
            return

        for ruleset_path in sorted(self._rules_dir.glob("*.json")):
            name = ruleset_path.stem  # e.g. "d0-kind1-gate"
            content_str = ruleset_path.read_text(encoding="utf-8")
            self._hashes[name] = hashlib.sha256(content_str.encode()).hexdigest()

            engine = ZenEngine()
            zen_content = self._zen_content_cls(content_str)
            self._engines[name] = {
                "engine": engine,
                "content": zen_content,
                "path": ruleset_path,
            }

    def evaluate(self, ruleset_name: str, context: dict[str, Any]) -> EvaluationResult:
        """Evaluate a context against a named ruleset.

        Args:
            ruleset_name: Stem of the .json file (e.g. "d0-kind1-gate")
            context: Input dict to evaluate

        Returns:
            EvaluationResult with output, hash, and version

        Raises:
            KeyError: If ruleset not found
            RuntimeError: If evaluation fails
        """
        if ruleset_name not in self._engines:
            available = list(self._engines.keys())
            raise KeyError(f"Ruleset '{ruleset_name}' not found. Available: {available}")

        entry = self._engines[ruleset_name]
        engine = entry["engine"]

        try:
            decision = engine.create_decision(entry["content"])
            result = decision.evaluate(context)

            return EvaluationResult(
                output=result.get("result", {}) if isinstance(result, dict) else dict(result),
                ruleset_hash=self._hashes[ruleset_name],
                engine_version=self._engine_version,
                ruleset_name=ruleset_name,
            )
        except Exception as e:
            raise RuntimeError(f"Rule evaluation failed for '{ruleset_name}': {e}") from e

    def get_ruleset_hash(self, ruleset_name: str) -> str:
        """Get the content hash of a loaded ruleset."""
        if ruleset_name not in self._hashes:
            raise KeyError(f"Ruleset '{ruleset_name}' not found")
        return self._hashes[ruleset_name]

    def reload(self) -> None:
        """Reload all rulesets from disk. Call after deploying new rules."""
        self._engines.clear()
        self._hashes.clear()
        self._load_all()

    @property
    def loaded_rulesets(self) -> list[str]:
        """Names of all loaded rulesets."""
        return list(self._engines.keys())
