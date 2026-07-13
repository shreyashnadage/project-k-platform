"""Platform data source for DPDP rights fulfillment.

Implements the DataSource protocol from dpdp-core, providing access/erasure/correction
operations against the platform's PostgreSQL tables.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update

from libs.db.models import (
    ConsentRecord,
    LoanApplicationRecord,
    VendorRecord,
)

logger = structlog.get_logger()


class PlatformDataSource:
    """DPDP rights fulfillment against the OCEN platform database."""

    source_name = "ocen_platform_db"

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def collect(self, data_principal_id: str) -> dict[str, Any]:
        """Gather all PII for an access request (Right to Access)."""
        async with self._session_factory() as session:
            vendor = await session.execute(
                select(VendorRecord).where(VendorRecord.gstin == data_principal_id)
            )
            vendor_row = vendor.scalar_one_or_none()

            loans = await session.execute(
                select(LoanApplicationRecord).where(
                    LoanApplicationRecord.vendor_gstin == data_principal_id
                )
            )
            loan_rows = loans.scalars().all()

            consents = await session.execute(
                select(ConsentRecord).where(ConsentRecord.data_principal_id == data_principal_id)
            )
            consent_rows = consents.scalars().all()

            return {
                "source": self.source_name,
                "vendor": {
                    "name": vendor_row.name if vendor_row else None,
                    "gstin": vendor_row.gstin if vendor_row else None,
                    "udyam_number": vendor_row.udyam_number if vendor_row else None,
                }
                if vendor_row
                else None,
                "loan_applications": [
                    {
                        "id": str(la.id),
                        "status": la.status,
                        "amount_requested": str(la.amount_requested),
                        "created_at": la.created_at.isoformat() if la.created_at else None,
                    }
                    for la in loan_rows
                ],
                "consents": [
                    {
                        "purpose": c.purpose,
                        "granted": c.granted,
                        "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                    }
                    for c in consent_rows
                ],
            }

    async def erase(self, data_principal_id: str) -> dict[str, Any]:
        """Pseudonymize PII for erasure request (not delete — RBI 7-year retention)."""
        async with self._session_factory() as session:
            hold = await self.has_legal_hold(data_principal_id, session)
            if hold:
                return {
                    "source": self.source_name,
                    "erased": False,
                    "skipped_reason": "legal_hold_active",
                }

            pseudo_id = _pseudonymize_token(data_principal_id)

            vendor = await session.execute(
                select(VendorRecord).where(VendorRecord.gstin == data_principal_id)
            )
            vendor_row = vendor.scalar_one_or_none()
            if vendor_row:
                vendor_row.name = f"Vendor-{pseudo_id[:8]}"
                vendor_row.gstin = f"V-{pseudo_id[:13]}"
                vendor_row.udyam_number = None
                vendor_row.name_enc = None
                vendor_row.gstin_enc = None
                vendor_row.gstin_idx = None
                vendor_row.udyam_number_enc = None
                vendor_row.udyam_number_idx = None

            await session.execute(
                update(LoanApplicationRecord)
                .where(LoanApplicationRecord.vendor_gstin == data_principal_id)
                .values(
                    vendor_gstin=f"V-{pseudo_id[:13]}",
                    vendor_gstin_enc=None,
                    vendor_gstin_idx=None,
                )
            )

            await session.execute(
                update(ConsentRecord)
                .where(ConsentRecord.data_principal_id == data_principal_id)
                .values(data_principal_id=f"P-{pseudo_id[:12]}")
            )

            await session.commit()
            logger.info("dpdp_erasure_completed", data_principal_id=data_principal_id[:4] + "***")

            return {
                "source": self.source_name,
                "erased": True,
                "pseudonymized_fields": ["name", "gstin", "udyam_number", "vendor_gstin"],
            }

    async def has_legal_hold(
        self,
        data_principal_id: str,
        session=None,
    ) -> bool:
        """Check if any loan is within the RBI retention window.

        Reads the "loan_application" retention_days from dpdp_config.yaml
        (same source services/la_orchestrator/activities.py::enforce_retention
        uses) instead of a hardcoded literal, so the two retention-enforcement
        code paths can't drift out of sync with each other again.
        """
        should_close = session is None
        if session is None:
            session = self._session_factory()

        try:
            from dpdp_core.config import get_config

            retention_days = next(
                policy.retention_days
                for policy in get_config().retention
                if policy.data_category == "loan_application"
            )
            cutoff = datetime.now(UTC) - timedelta(days=retention_days)
            result = await session.execute(
                select(LoanApplicationRecord.id).where(
                    LoanApplicationRecord.vendor_gstin == data_principal_id,
                    LoanApplicationRecord.status.in_(["disbursed", "repaying", "closed"]),
                    LoanApplicationRecord.created_at > cutoff,
                )
            )
            return result.first() is not None
        finally:
            if should_close:
                await session.close()


def _pseudonymize_token(value: str) -> str:
    """Deterministic pseudonymization token from a value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
