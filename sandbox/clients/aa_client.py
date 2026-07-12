"""Sandbox Account Aggregator client — simulates Setu/Perfios responses."""

from __future__ import annotations

import asyncio
import uuid

import structlog

from libs.integrations.protocols import ConsentResponse, ConsentStatus, FinancialData
from sandbox.config import SANDBOX_AA_AUTO_APPROVE, SANDBOX_RESPONSE_DELAY_MS

logger = structlog.get_logger()

SANDBOX_BANK_STATEMENT = {
    "account_type": "SAVINGS",
    "bank_name": "State Bank of India",
    "months": [
        {"month": "2026-01", "credit": 850000, "debit": 720000, "balance": 430000},
        {"month": "2026-02", "credit": 920000, "debit": 780000, "balance": 570000},
        {"month": "2026-03", "credit": 780000, "debit": 650000, "balance": 700000},
        {"month": "2026-04", "credit": 1100000, "debit": 900000, "balance": 900000},
        {"month": "2026-05", "credit": 950000, "debit": 820000, "balance": 1030000},
        {"month": "2026-06", "credit": 870000, "debit": 750000, "balance": 1150000},
    ],
}

SANDBOX_GST_RETURNS = [
    {"period": "2026-01", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 850000},
    {"period": "2026-02", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 920000},
    {"period": "2026-03", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 780000},
    {"period": "2026-04", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 1100000},
    {"period": "2026-05", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 950000},
    {"period": "2026-06", "gstr1_filed": True, "gstr3b_filed": False, "turnover": 870000},
]


class SandboxAAClient:
    """Sandbox AA client returning realistic Kolhapur-belt MSME financial data."""

    def __init__(self) -> None:
        self._consents: dict[str, str] = {}

    async def _simulate_delay(self) -> None:
        if SANDBOX_RESPONSE_DELAY_MS > 0:
            await asyncio.sleep(SANDBOX_RESPONSE_DELAY_MS / 1000)

    async def create_consent(
        self, vendor_gstin: str, purpose: str, duration_months: int
    ) -> ConsentResponse:
        await self._simulate_delay()
        consent_id = f"sandbox-consent-{uuid.uuid4().hex[:8]}"
        status = "approved" if SANDBOX_AA_AUTO_APPROVE else "pending"
        self._consents[consent_id] = status
        logger.info(
            "sandbox_aa_consent_created",
            consent_id=consent_id,
            gstin=vendor_gstin,
            status=status,
        )
        return ConsentResponse(
            consent_id=consent_id,
            redirect_url=f"https://sandbox-aa.local/consent/{consent_id}",
            status=status,
        )

    async def check_consent_status(self, consent_id: str) -> ConsentStatus:
        await self._simulate_delay()
        status = self._consents.get(consent_id, "not_found")
        return ConsentStatus(
            consent_id=consent_id,
            status=status,
            approved_at="2026-07-12T10:00:00Z" if status == "approved" else None,
        )

    async def fetch_financial_data(self, consent_id: str) -> FinancialData:
        await self._simulate_delay()
        logger.info("sandbox_aa_data_fetched", consent_id=consent_id)
        return FinancialData(
            consent_id=consent_id,
            months_available=6,
            bank_statements=[SANDBOX_BANK_STATEMENT],
            gst_returns=SANDBOX_GST_RETURNS,
        )
