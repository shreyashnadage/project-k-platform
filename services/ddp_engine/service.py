"""DDP Engine service — computes derived attributes and risk flags.

This is the D2 gate logic — computing derived data that lenders use for
underwriting. We compute and provide; we NEVER make the lending decision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import structlog

from .models import (
    DerivedAttributes,
    DerivedDataRequest,
    DerivedDataResponse,
    RiskFlag,
)

logger = structlog.get_logger()


class DDPEngineService:
    """Computes derived attributes for the DDP function."""

    def __init__(self) -> None:
        self._ruleset_hash = "ddp-derived-v1-placeholder"

    def compute_derived_data(self, request: DerivedDataRequest) -> DerivedDataResponse:
        attributes = self._compute_attributes(request)
        risk_flags = self._evaluate_risk_flags(attributes, request)

        logger.info(
            "derived_data_computed",
            loan_application_id=str(request.loan_application_id),
            flag_count=len(risk_flags),
        )

        return DerivedDataResponse(
            loan_application_id=request.loan_application_id,
            vendor_gstin=request.vendor_gstin,
            anchor_gstin=request.anchor_gstin,
            attributes=attributes,
            risk_flags=risk_flags,
            ruleset_hash=self._ruleset_hash,
            computed_at=datetime.now(UTC),
        )

    def _compute_attributes(self, request: DerivedDataRequest) -> DerivedAttributes:
        # Stub computations — production pulls from GST returns, bank statements, trade history
        return DerivedAttributes(
            dso_days=45,
            dpo_days=30,
            ccc_days=15,
            revenue_concentration=Decimal("35.5"),
            dilution_rate=Decimal("2.1"),
            anchor_payment_history_score=Decimal("85.0"),
            gst_compliance_score=Decimal("92.0"),
            vintage_months=request.gst_returns_months,
        )

    def _evaluate_risk_flags(
        self, attributes: DerivedAttributes, request: DerivedDataRequest
    ) -> list[RiskFlag]:
        flags: list[RiskFlag] = []

        if attributes.revenue_concentration > Decimal("50"):
            flags.append(
                RiskFlag(
                    flag_code="HIGH_CONCENTRATION",
                    severity="high",
                    description="Revenue concentration from single anchor exceeds 50%",
                    threshold="50%",
                    actual_value=str(attributes.revenue_concentration) + "%",
                )
            )

        if attributes.dso_days > 60:
            flags.append(
                RiskFlag(
                    flag_code="HIGH_DSO",
                    severity="medium",
                    description="Days Sales Outstanding exceeds 60 days",
                    threshold="60",
                    actual_value=str(attributes.dso_days),
                )
            )

        if attributes.dilution_rate > Decimal("5"):
            flags.append(
                RiskFlag(
                    flag_code="HIGH_DILUTION",
                    severity="medium",
                    description="Invoice dilution rate exceeds 5%",
                    threshold="5%",
                    actual_value=str(attributes.dilution_rate) + "%",
                )
            )

        if attributes.gst_compliance_score < Decimal("70"):
            flags.append(
                RiskFlag(
                    flag_code="LOW_GST_COMPLIANCE",
                    severity="high",
                    description="GST compliance score below 70",
                    threshold="70",
                    actual_value=str(attributes.gst_compliance_score),
                )
            )

        if attributes.vintage_months < 6:
            flags.append(
                RiskFlag(
                    flag_code="LOW_VINTAGE",
                    severity="medium",
                    description="Relationship vintage below 6 months",
                    threshold="6",
                    actual_value=str(attributes.vintage_months),
                )
            )

        return flags
