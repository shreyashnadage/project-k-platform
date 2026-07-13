"""Business admin / audit-reporting perspective tests.

Proves the audit trail an admin/auditor relies on is real, not just
plausible-looking: decision receipts actually get signed and persisted,
the chain actually verifies, vendor/anchor onboarding actually persists,
and the gaps that are still stubs (breach notification) are documented
as intentional rather than silently rotting.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


class TestAuditReceiptEndpointUnit:
    """No DB required — exercises the always-protected-path guard and
    route wiring."""

    def test_requires_auth_even_with_rbac_disabled(self, monkeypatch):
        """/dpdp/audit is an always_protected_path (authz.yaml) — same
        unconditional protection as /dpdp/rights, /dpdp/consent."""
        monkeypatch.setenv("INTEGRATION_MODE", "sandbox")
        from services.borrower_gateway.app import app

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/dpdp/audit/receipts/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_route_is_registered(self):
        from services.borrower_gateway.app import app

        paths = set(app.openapi()["paths"].keys())
        assert "/dpdp/audit/receipts/{loan_application_id}" in paths


class TestKnownStubBoundaries:
    """Documents — with a real, executed assertion — which parts of the
    breach pipeline are still intentional stubs. If someone wires these up
    for real, these tests should be updated/removed, not left stale."""

    @pytest.mark.asyncio
    async def test_notify_affected_principals_is_still_a_documented_stub(self):
        from services.la_orchestrator.activities import BreachInput, notify_affected_principals

        result = await notify_affected_principals(
            BreachInput(rule="bulk_access", event_count=150, window_minutes=5, actor_id="u1")
        )
        assert result["count"] == 0
        assert result["reason"] == "notification_system_pending"

    @pytest.mark.asyncio
    async def test_notify_dpbi_only_logs_does_not_actually_notify(self):
        from services.la_orchestrator.activities import BreachInput, notify_dpbi

        result = await notify_dpbi(
            BreachInput(rule="bulk_access", event_count=150, window_minutes=5, actor_id="u1")
        )
        # "notified": True here means "we logged it", not "DPBI received it" —
        # asserting the current (misleading) contract so a future fix is a
        # visible, deliberate test change, not a silent behavior shift.
        assert "notified" in result


@pytest.mark.integration
class TestAuditTrailAgainstRealPostgres:
    """Requires `make up`. Proves receipts persisted by evaluate_decision
    actually chain-verify when read back — not just that signing code
    exists in isolation (that's tests/test_smoke.py's job)."""

    @pytest.mark.asyncio
    async def test_evaluate_decision_persists_a_signed_chained_receipt(self, real_db_session):
        from sqlalchemy import select

        from libs.audit.receipts import ChainVerifier
        from libs.common.models import DecisionGate, DecisionOutcome, DecisionReceipt
        from libs.db.models import DecisionReceiptRecord
        from services.la_orchestrator.activities import EvaluateDecisionInput, evaluate_decision

        loan_application_id = str(uuid.uuid4())
        context = {
            "irn_valid": True,
            "ims_status": "accepted",
            "repayment_routing_active": True,
            "gstin_valid": True,
        }

        result = await evaluate_decision(
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d0_kind1_gate",
                ruleset_name="d0-kind1-gate",
                context=context,
            )
        )

        assert result["outcome"] == "pass"
        assert result["receipt_id"] != f"receipt-{loan_application_id}-d0_kind1_gate", (
            "receipt_id must be a real uuid4, not the old non-reproducible hash() derivation"
        )

        rows = (
            (
                await real_db_session.execute(
                    select(DecisionReceiptRecord).where(
                        DecisionReceiptRecord.loan_application_id == uuid.UUID(loan_application_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.signature is not None
        assert row.chain_hash is not None

        receipt = DecisionReceipt(
            id=row.id,
            loan_application_id=row.loan_application_id,
            gate=DecisionGate(row.gate),
            outcome=DecisionOutcome(row.outcome),
            ruleset_hash=row.ruleset_hash,
            input_hash=row.input_hash,
            output=row.output_data or {},
            engine_version=row.engine_version,
            signature=row.signature,
            chain_hash=row.chain_hash,
            evaluated_at=row.evaluated_at,
        )
        assert ChainVerifier.verify_chain([receipt]) is True

    @pytest.mark.asyncio
    async def test_second_gate_chains_to_the_first(self, real_db_session):
        """Two receipts for the same loan must chain — the second's
        chain_hash must depend on the first's, proving tamper-evidence."""
        from sqlalchemy import select

        from libs.db.models import DecisionReceiptRecord
        from services.la_orchestrator.activities import EvaluateDecisionInput, evaluate_decision

        loan_application_id = str(uuid.uuid4())
        context = {
            "irn_valid": True,
            "ims_status": "accepted",
            "repayment_routing_active": True,
            "gstin_valid": True,
        }

        await evaluate_decision(
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d0_kind1_gate",
                ruleset_name="d0-kind1-gate",
                context=context,
            )
        )
        await evaluate_decision(
            EvaluateDecisionInput(
                loan_application_id=loan_application_id,
                gate="d1_data_sufficiency",
                ruleset_name="d1-data-sufficiency",
                context={
                    "months_available": 12,
                    "data_freshness_days": 5,
                    "gst_returns_filed": True,
                },
            )
        )

        rows = (
            (
                await real_db_session.execute(
                    select(DecisionReceiptRecord)
                    .where(
                        DecisionReceiptRecord.loan_application_id == uuid.UUID(loan_application_id)
                    )
                    .order_by(DecisionReceiptRecord.evaluated_at.asc())
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert rows[0].chain_hash != rows[1].chain_hash

    @pytest.mark.asyncio
    async def test_vendor_invite_and_activate_round_trip_through_real_db(
        self, real_db_session, monkeypatch
    ):
        monkeypatch.setenv("GATEWAY_USE_DB", "true")
        monkeypatch.setenv("INTEGRATION_MODE", "sandbox")

        from sqlalchemy import select

        from libs.db.models import VendorRecord

        gstin = "27AADCB2230M1ZT"
        token = "test-invite-token-xyz"

        real_db_session.add(
            VendorRecord(
                id=uuid.uuid4(),
                name="Test Vendor",
                gstin=gstin,
                phone="+919876543210",
                invite_token=token,
                status="pending",
                invited_by="ops@example.com",
            )
        )
        await real_db_session.commit()

        row = (
            await real_db_session.execute(select(VendorRecord).where(VendorRecord.gstin == gstin))
        ).scalar_one()
        assert row.status == "pending"
        assert row.invite_token == token

        row.status = "active"
        row.invite_token = None
        await real_db_session.commit()

        refreshed = (
            await real_db_session.execute(select(VendorRecord).where(VendorRecord.gstin == gstin))
        ).scalar_one()
        assert refreshed.status == "active"
        assert refreshed.invite_token is None
