"""Mock GST/e-invoicing client — simulates IRN validation and IMS lookup."""

from __future__ import annotations

import re

import structlog

from libs.integrations.protocols import GSTINValidation, IMSStatus, IRNValidation

logger = structlog.get_logger()

GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}[Z]{1}[A-Z0-9]{1}$")
IRN_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class MockGSTClient:
    """Mock GST client — validates format and returns realistic responses."""

    async def validate_irn(self, irn: str) -> IRNValidation:
        valid = bool(IRN_PATTERN.match(irn))
        logger.info("mock_irn_validated", irn=irn[:16] + "...", valid=valid)
        return IRNValidation(
            irn=irn,
            valid=valid,
            invoice_date="2026-06-15" if valid else None,
            seller_gstin="27AADCB2230M1ZT" if valid else None,
        )

    async def check_ims_status(self, irn: str, buyer_gstin: str) -> IMSStatus:
        valid_irn = bool(IRN_PATTERN.match(irn))
        status = "accepted" if valid_irn else "pending"
        logger.info("mock_ims_checked", irn=irn[:16] + "...", status=status)
        return IMSStatus(
            irn=irn,
            status=status,
            action_date="2026-06-20" if status == "accepted" else None,
        )

    async def validate_gstin(self, gstin: str) -> GSTINValidation:
        valid = bool(GSTIN_PATTERN.match(gstin))
        return GSTINValidation(
            gstin=gstin,
            valid=valid,
            trade_name="Mock Enterprise Pvt. Ltd." if valid else None,
            status="Active" if valid else "Invalid",
        )
