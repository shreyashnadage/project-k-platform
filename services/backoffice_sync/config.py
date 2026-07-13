"""Configuration for Back-Office Sync Service."""

from __future__ import annotations

import os

from libs.common.events import EventType

_DEFAULT_WEBHOOK_SECRET = "dev-webhook-secret"

BACKOFFICE_URL = os.environ.get("BACKOFFICE_URL", "http://localhost:8080")
BACKOFFICE_API_KEY = os.environ.get("BACKOFFICE_API_KEY", "")
BACKOFFICE_API_SECRET = os.environ.get("BACKOFFICE_API_SECRET", "")
WEBHOOK_SECRET = os.environ.get("BACKOFFICE_WEBHOOK_SECRET", _DEFAULT_WEBHOOK_SECRET)

_integration_mode = os.environ.get("INTEGRATION_MODE", "")
if WEBHOOK_SECRET == _DEFAULT_WEBHOOK_SECRET and _integration_mode != "sandbox":
    raise RuntimeError(
        "BACKOFFICE_WEBHOOK_SECRET is not set, and the known dev-only default "
        f"({_DEFAULT_WEBHOOK_SECRET!r}) would be used to sign outbound webhooks "
        "outside INTEGRATION_MODE=sandbox — deliveries will silently fail if the "
        "receiving side expects a real secret. Set BACKOFFICE_WEBHOOK_SECRET "
        "explicitly, or set INTEGRATION_MODE=sandbox for local development."
    )

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "ocen.trade-events.v1")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "backoffice-sync-consumer")

# References EventType members (libs/common/events.py — "the SINGLE source
# of truth" per that file's own docstring) instead of re-typed literals, so
# a rename/typo there is a real ImportError here, not a silently-missed event.
EVENTS_TO_FORWARD = {
    EventType.INVOICE_KIND1_ATTESTED.value,
    EventType.LOAN_APPLICATION_CREATED.value,
    EventType.LOAN_DECISION_EVALUATED.value,
    EventType.LOAN_SUBMITTED_TO_LENDER.value,
    EventType.LOAN_OFFER_RECEIVED.value,
    EventType.LOAN_OFFER_ACCEPTED.value,
    EventType.LOAN_DISBURSED.value,
    EventType.LOAN_REPAYMENT_OBSERVED.value,
    EventType.LOAN_CLOSED.value,
    EventType.LOAN_REJECTED.value,
    EventType.VENDOR_ONBOARDED.value,
    EventType.VENDOR_INVITED.value,
    EventType.VENDOR_ACTIVATED.value,
    EventType.ANCHOR_ONBOARDED.value,
    EventType.OPS_HOLD_APPLIED.value,
    EventType.OPS_HOLD_RELEASED.value,
    EventType.OPS_FLAG_ADDED.value,
    EventType.OPS_ESCALATED.value,
}
