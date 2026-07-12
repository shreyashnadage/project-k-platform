"""Configuration for Frappe Sync Service."""

from __future__ import annotations

import os

FRAPPE_URL = os.environ.get("FRAPPE_URL", "http://localhost:8080")
FRAPPE_API_KEY = os.environ.get("FRAPPE_API_KEY", "")
FRAPPE_API_SECRET = os.environ.get("FRAPPE_API_SECRET", "")
WEBHOOK_SECRET = os.environ.get("FRAPPE_WEBHOOK_SECRET", "dev-webhook-secret")

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "ocen.trade-events.v1")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "frappe-sync-consumer")

EVENTS_TO_FORWARD = {
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
