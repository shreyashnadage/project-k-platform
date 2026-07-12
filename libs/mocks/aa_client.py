"""Mock Account Aggregator client — simulates Setu/Perfios responses."""

from __future__ import annotations

import uuid

import structlog

from libs.integrations.protocols import ConsentResponse, ConsentStatus, FinancialData

logger = structlog.get_logger()

MOCK_BANK_STATEMENT = {
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

MOCK_GST_RETURNS = [
    {"period": "2026-01", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 850000},
    {"period": "2026-02", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 920000},
    {"period": "2026-03", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 780000},
    {"period": "2026-04", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 1100000},
    {"period": "2026-05", "gstr1_filed": True, "gstr3b_filed": True, "turnover": 950000},
    {"period": "2026-06", "gstr1_filed": True, "gstr3b_filed": False, "turnover": 870000},
]


class MockAAClient:
    """Mock AA client returning realistic Kolhapur-belt MSME financial data."""

    def __init__(self) -> None:
        self._consents: dict[str, str] = {}

    async def create_consent(
        self, vendor_gstin: str, purpose: str, duration_months: int
    ) -> ConsentResponse:
        consent_id = f"mock-consent-{uuid.uuid4().hex[:8]}"
        self._consents[consent_id] = "approved"
        logger.info("mock_aa_consent_created", consent_id=consent_id, gstin=vendor_gstin)
        return ConsentResponse(
            consent_id=consent_id,
            redirect_url=f"https://mock-aa.example/consent/{consent_id}",
            status="approved",
        )

    async def check_consent_status(self, consent_id: str) -> ConsentStatus:
        status = self._consents.get(consent_id, "not_found")
        return ConsentStatus(
            consent_id=consent_id,
            status=status,
            approved_at="2026-07-12T10:00:00Z" if status == "approved" else None,
        )

    async def fetch_financial_data(self, consent_id: str) -> FinancialData:
        logger.info("mock_aa_data_fetched", consent_id=consent_id)
        return FinancialData(
            consent_id=consent_id,
            months_available=6,
            bank_statements=[MOCK_BANK_STATEMENT],
            gst_returns=MOCK_GST_RETURNS,
        )
