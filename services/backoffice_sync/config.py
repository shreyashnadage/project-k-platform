"""Configuration for Back-Office Sync Service."""

from __future__ import annotations

import os

BACKOFFICE_URL = os.environ.get("BACKOFFICE_URL", "http://localhost:8080")
BACKOFFICE_API_KEY = os.environ.get("BACKOFFICE_API_KEY", "")
BACKOFFICE_API_SECRET = os.environ.get("BACKOFFICE_API_SECRET", "")
WEBHOOK_SECRET = os.environ.get("BACKOFFICE_WEBHOOK_SECRET", "dev-webhook-secret")

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "ocen.trade-events.v1")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "backoffice-sync-consumer")

EVENTS_TO_FORWARD = {
    "invoice.kind1_attested",
    "loan.application_created",
    "loan.decision_evaluated",
    "loan.submitted_to_lender",
    "loan.offer_received",
    "loan.offer_accepted",
    "loan.disbursed",
    "loan.repayment_observed",
    "loan.closed",
    "loan.rejected",
    "vendor.onboarded",
    "vendor.invited",
    "vendor.activated",
    "anchor.onboarded",
    "ops.hold_applied",
    "ops.hold_released",
    "ops.flag_added",
    "ops.escalated",
}
