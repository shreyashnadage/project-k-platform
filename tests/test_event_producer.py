"""Integration test for event producer — requires Redpanda running."""

from __future__ import annotations

import json
import time

import pytest

from libs.common.events import EventType, invoice_kind1_attested

pytestmark = pytest.mark.integration


@pytest.fixture
def producer():
    from libs.common.event_producer import EventProducer

    p = EventProducer(
        bootstrap_servers="localhost:19092",
        topic="ocen.trade-events.v1",
    )
    yield p
    p.flush()


@pytest.fixture
def consumer():
    from confluent_kafka import Consumer

    c = Consumer(
        {
            "bootstrap.servers": "localhost:19092",
            "group.id": "test-consumer-group",
            "auto.offset.reset": "earliest",
        }
    )
    c.subscribe(["ocen.trade-events.v1"])
    yield c
    c.close()


def test_produce_and_consume_event(producer, consumer):
    """Round-trip: produce a TradeEvent, consume it back."""
    event = invoice_kind1_attested(
        invoice_id="inv-test-001",
        anchor_id="anchor-001",
        vendor_id="vendor-001",
    )

    producer.produce(event)
    producer.flush()

    # Poll for the message (timeout after 10s)
    msg = None
    deadline = time.time() + 10
    while time.time() < deadline:
        msg = consumer.poll(1.0)
        if msg is not None and msg.error() is None:
            break

    assert msg is not None and msg.error() is None
    payload = json.loads(msg.value().decode("utf-8"))
    assert payload["event_type"] == EventType.INVOICE_KIND1_ATTESTED.value
    assert payload["payload"]["invoice_id"] == "inv-test-001"
