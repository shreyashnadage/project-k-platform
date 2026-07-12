"""Redpanda consumer that forwards platform events to Frappe as webhooks.

Run standalone: uv run python -m services.frappe_sync.consumer
"""

from __future__ import annotations

import asyncio
import json
import signal

import structlog

from .config import (
    EVENTS_TO_FORWARD,
    KAFKA_BOOTSTRAP,
    KAFKA_GROUP_ID,
    KAFKA_TOPIC,
)
from .webhook_client import FrappeWebhookClient

logger = structlog.get_logger()


class FrappeSyncConsumer:
    """Consumes events from Redpanda and pushes webhooks to Frappe."""

    def __init__(self) -> None:
        self._webhook_client = FrappeWebhookClient()
        self._running = False

    async def start(self) -> None:
        """Start the consumer loop."""
        from confluent_kafka import Consumer, KafkaError

        conf = {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": KAFKA_GROUP_ID,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,
        }

        consumer = Consumer(conf)
        consumer.subscribe([KAFKA_TOPIC])
        self._running = True

        logger.info(
            "frappe_sync_consumer_started",
            topic=KAFKA_TOPIC,
            group_id=KAFKA_GROUP_ID,
            bootstrap=KAFKA_BOOTSTRAP,
        )

        try:
            while self._running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("kafka_error", error=str(msg.error()))
                    continue

                try:
                    event = json.loads(msg.value().decode("utf-8"))
                    event_type = event.get("event_type", "")

                    if event_type in EVENTS_TO_FORWARD:
                        delivered = await self._webhook_client.deliver(
                            event_type=event_type,
                            payload=event,
                        )
                        if not delivered:
                            logger.error(
                                "webhook_dead_letter",
                                event_type=event_type,
                                event_id=event.get("event_id"),
                            )
                except json.JSONDecodeError:
                    logger.error("invalid_event_json", raw=msg.value()[:200])
                except Exception:
                    logger.exception("event_processing_error")

        finally:
            consumer.close()
            logger.info("frappe_sync_consumer_stopped")

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    consumer = FrappeSyncConsumer()

    import contextlib

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, consumer.stop)

    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
