"""Retention handlers for DPDP data categories.

Each handler implements the enforcement logic for a specific data category
as defined in dpdp_config.yaml retention policies.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from libs.db.models import LoanApplicationRecord, VendorRecord

logger = structlog.get_logger()

_handlers: dict[str, RetentionHandler] = {}


class RetentionHandler:
    """Base class for retention enforcement handlers."""

    async def enforce(self, retention_days: int) -> int:
        raise NotImplementedError


class LoanApplicationRetentionHandler(RetentionHandler):
    """Pseudonymize loan applications older than retention period (post-closure)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def enforce(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        count = 0

        async with self._session_factory() as session:
            result = await session.execute(
                select(LoanApplicationRecord).where(
                    LoanApplicationRecord.status == "closed",
                    LoanApplicationRecord.updated_at < cutoff,
                    LoanApplicationRecord.vendor_gstin.not_like("V-%"),
                )
            )
            rows = result.scalars().all()

            for row in rows:
                pseudo = hashlib.sha256(row.vendor_gstin.encode()).hexdigest()
                row.vendor_gstin = f"V-{pseudo[:13]}"
                row.vendor_gstin_enc = None
                row.vendor_gstin_idx = None
                row.anchor_gstin = f"A-{hashlib.sha256(row.anchor_gstin.encode()).hexdigest()[:13]}"
                row.anchor_gstin_enc = None
                row.anchor_gstin_idx = None
                count += 1

            if count:
                await session.commit()
                logger.info("retention_loan_applications", pseudonymized=count)

        return count


class VendorContactRetentionHandler(RetentionHandler):
    """Anonymize vendor contact info for inactive vendors past retention."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def enforce(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        count = 0

        async with self._session_factory() as session:
            result = await session.execute(
                select(VendorRecord).where(
                    VendorRecord.onboarded_at < cutoff,
                    VendorRecord.gstin.not_like("V-%"),
                )
            )
            rows = result.scalars().all()

            for row in rows:
                # Check if vendor has any active loans
                active = await session.execute(
                    select(LoanApplicationRecord.id).where(
                        LoanApplicationRecord.vendor_gstin == row.gstin,
                        LoanApplicationRecord.status.in_(["created", "disbursed", "repaying"]),
                    )
                )
                if active.first():
                    continue

                pseudo = hashlib.sha256(row.gstin.encode()).hexdigest()
                row.name = f"Vendor-{pseudo[:8]}"
                row.gstin = f"V-{pseudo[:13]}"
                row.udyam_number = None
                row.name_enc = None
                row.gstin_enc = None
                row.gstin_idx = None
                row.udyam_number_enc = None
                row.udyam_number_idx = None
                count += 1

            if count:
                await session.commit()
                logger.info("retention_vendor_contacts", anonymized=count)

        return count


def register_handlers(session_factory) -> None:
    """Register all retention handlers with a shared session factory."""
    _handlers["loan_application"] = LoanApplicationRetentionHandler(session_factory)
    _handlers["vendor_contact"] = VendorContactRetentionHandler(session_factory)


def get_retention_handler(category: str) -> RetentionHandler | None:
    """Get the retention handler for a given data category."""
    if not _handlers:
        from libs.integrations.factory import get_db_session_factory

        register_handlers(get_db_session_factory())
    return _handlers.get(category)
