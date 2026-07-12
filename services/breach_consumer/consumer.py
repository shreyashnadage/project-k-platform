"""Breach detection consumer — watches audit log topic for suspicious patterns.

Consumes from dpdp.audit-log.v1, applies sliding-window counters per rule,
and triggers BreachDetectionWorkflow when thresholds are breached.

Usage: uv run python -m services.breach_consumer.consumer
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import structlog
import yaml
from temporalio.client import Client as TemporalClient

logger = structlog.get_logger()

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
AUDIT_TOPIC = os.environ.get("DPDP_AUDIT_TOPIC", "dpdp.audit-log.v1")
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "loan-origination")
CONFIG_PATH = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")


@dataclass
class SlidingWindow:
    """Sliding window counter for breach detection."""

    window_seconds: int
    threshold: int
    events: list[float] = field(default_factory=list)

    def add(self, timestamp: float | None = None) -> bool:
        """Add an event and return True if threshold is breached."""
        now = timestamp or time.time()
        self.events.append(now)
        cutoff = now - self.window_seconds
        self.events = [t for t in self.events if t > cutoff]
        return len(self.events) >= self.threshold

    @property
    def count(self) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        self.events = [t for t in self.events if t > cutoff]
        return len(self.events)


def load_detection_rules() -> dict[str, dict]:
    """Load breach detection rules from dpdp_config.yaml."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    rules = {}
    for rule in config.get("breach", {}).get("detection_rules", []):
        rules[rule["rule"]] = rule
    return rules


def map_event_to_rule(event_type: str) -> str | None:
    """Map an audit event type to a detection rule."""
    mapping = {
        "bulk_pii_access": "bulk_access",
        "pii_export": "export_without_dsr",
        "auth_failed": "failed_auth",
    }
    return mapping.get(event_type)


async def run_consumer() -> None:
    """Main consumer loop."""
    rules = load_detection_rules()
    windows: dict[str, SlidingWindow] = {}

    for rule_name, rule_config in rules.items():
        windows[rule_name] = SlidingWindow(
            window_seconds=rule_config["window_minutes"] * 60,
            threshold=rule_config["threshold"],
        )

    logger.info(
        "breach_consumer_starting",
        topic=AUDIT_TOPIC,
        rules=list(rules.keys()),
    )

    temporal = await TemporalClient.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)

    try:
        from confluent_kafka import Consumer

        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "dpdp-breach-detector",
            "auto.offset.reset": "latest",
        })
        consumer.subscribe([AUDIT_TOPIC])

        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.warning("kafka_consumer_error", error=str(msg.error()))
                continue

            try:
                import orjson

                event = orjson.loads(msg.value())
                event_type = event.get("event_type", "")
                actor_id = event.get("actor_id", "")

                rule_name = map_event_to_rule(event_type)
                if not rule_name or rule_name not in windows:
                    continue

                breached = windows[rule_name].add()
                if breached:
                    logger.warning(
                        "breach_threshold_exceeded",
                        rule=rule_name,
                        count=windows[rule_name].count,
                        actor_id=actor_id,
                    )

                    from services.la_orchestrator.workflows import (
                        BreachDetectionInput,
                    )

                    workflow_id = f"breach-{rule_name}-{int(time.time())}"
                    await temporal.start_workflow(
                        "BreachDetectionWorkflow",
                        BreachDetectionInput(
                            rule=rule_name,
                            event_count=windows[rule_name].count,
                            window_minutes=rules[rule_name]["window_minutes"],
                            actor_id=actor_id,
                        ),
                        id=workflow_id,
                        task_queue=TASK_QUEUE,
                    )
                    logger.info("breach_workflow_triggered", workflow_id=workflow_id)

                    # Reset window after triggering to avoid spam
                    windows[rule_name] = SlidingWindow(
                        window_seconds=rules[rule_name]["window_minutes"] * 60,
                        threshold=rules[rule_name]["threshold"],
                    )

            except Exception as e:
                logger.error("breach_event_processing_failed", error=str(e))

    except ImportError:
        logger.error(
            "confluent_kafka_not_installed",
            hint="pip install confluent-kafka",
        )
        raise


async def main() -> None:
    await run_consumer()


if __name__ == "__main__":
    asyncio.run(main())
