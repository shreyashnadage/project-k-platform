"""Event producer for the Redpanda trade-event stream.

Implements the transactional outbox pattern:
1. Write event to Postgres outbox table in the same transaction as the domain change
2. A separate relay process reads the outbox and publishes to Redpanda
3. This ensures exactly-once semantics between DB and event stream

For simplicity, this module also supports direct Kafka production
(at-least-once with idempotent producer) for events that don't
need transactional guarantees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
import structlog
from confluent_kafka import Producer
from dpdp_core.pii.event_scanner import scan_payload

if TYPE_CHECKING:
    from libs.common.events import TradeEvent

logger = structlog.get_logger()

TRADE_EVENTS_TOPIC = "ocen.trade-events.v1"


class EventProducer:
    """Publishes TradeEvents to Redpanda."""

    def __init__(self, bootstrap_servers: str = "localhost:19092") -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "enable.idempotence": True,  # Exactly-once per partition
                "acks": "all",
                "linger.ms": 5,
                "compression.type": "zstd",
            }
        )

    def publish(self, event: TradeEvent) -> None:
        """Publish a trade event to Redpanda.

        Key: {entity_type}:{entity_id} — ensures ordering per entity.
        Payload is scanned for PII before emission — any detected PII
        is replaced with <REDACTED:ENTITY_TYPE> markers.
        """
        event_data = event.model_dump(mode="json")
        event_data["payload"] = scan_payload(event_data.get("payload", {}))
        key = event.topic_key().encode("utf-8")
        value = orjson.dumps(event_data)

        self._producer.produce(
            topic=TRADE_EVENTS_TOPIC,
            key=key,
            value=value,
            headers={
                "event_type": event.event_type.value.encode(),
                "schema_version": event.schema_version.encode(),
                "correlation_id": str(event.correlation_id or "").encode(),
            },
            callback=self._delivery_callback,
        )
        self._producer.poll(0)  # Trigger delivery callbacks

    def flush(self, timeout: float = 10.0) -> int:
        """Flush pending events. Returns number of messages still in queue."""
        return self._producer.flush(timeout)

    @staticmethod
    def _delivery_callback(err: Any, msg: Any) -> None:
        if err:
            logger.error("event_delivery_failed", error=str(err), topic=msg.topic())
        else:
            logger.debug(
                "event_delivered",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )
