"""Test for Phase 5: invoice.kind1_attested must reach the back-office.

Previously this event existed in libs/common/events.py's EventType enum
but was never added to the back-office sync consumer's forward list — the
back-office saw generic D0 gate pass/fail/flag outcomes (via
loan.decision_evaluated) but never the underlying IRN/IMS/routing detail
that explains why. See docs/frappe-crm-loan-management-spec.md.
"""

from __future__ import annotations


def test_kind1_attested_event_is_forwarded():
    from services.backoffice_sync.config import EVENTS_TO_FORWARD

    assert "invoice.kind1_attested" in EVENTS_TO_FORWARD


def test_kind1_attested_matches_the_real_event_type_enum():
    from libs.common.events import EventType
    from services.backoffice_sync.config import EVENTS_TO_FORWARD

    assert EventType.INVOICE_KIND1_ATTESTED.value in EVENTS_TO_FORWARD
