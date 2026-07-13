"""DDP Engine service — computes derived attributes and risk flags.

This is the D2 gate logic — computing derived data that lenders use for
underwriting. We compute and provide; we NEVER make the lending decision.

Risk-flag thresholds live in ONE place — rules/d2-derived-flags.json — and
are evaluated via the same ZenDecisionEngine the Temporal workflow's D2
gate uses (services/la_orchestrator/activities.py). Previously this service
hardcoded its own, different thresholds in Python; that drift is what this
rewrite fixes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import structlog

from libs.zen_rules.engine import ZenDecisionEngine

from .models import (
    DerivedAttributes,
    DerivedDataRequest,
    DerivedDataResponse,
    RiskFlag,
)

logger = structlog.get_logger()

_RULESET_NAME = "d2-derived-flags"

# Maps the JDM ruleset's lowercase flag names to the uppercase codes this
# API has always returned (kept for backward compatibility with existing
# consumers), plus a human-readable description/threshold for each.
_FLAG_META = {
    "high_concentration": (
        "HIGH_CONCENTRATION",
        "Revenue concentration from single anchor exceeds 80%",
        "80%",
    ),
    "elevated_dso": ("HIGH_DSO", "Days Sales Outstanding exceeds 90 days", "90"),
    "high_dilution": ("HIGH_DILUTION", "Invoice dilution rate exceeds 15%", "15%"),
    "anchor_payment_delays": (
        "ANCHOR_PAYMENT_DELAYS",
        "Anchor's average payment delay exceeds 30 days",
        "30",
    ),
    "low_gst_compliance": ("LOW_GST_COMPLIANCE", "GST compliance score below 70", "70"),
    "low_vintage": ("LOW_VINTAGE", "Relationship vintage below 6 months", "6"),
}


class DDPEngineService:
    """Computes derived attributes for the DDP function."""

    def __init__(self, engine: ZenDecisionEngine | None = None) -> None:
        self._engine = engine or ZenDecisionEngine("rules/")
        self._ruleset_hash = self._engine.get_ruleset_hash(_RULESET_NAME)

    def compute_derived_data(self, request: DerivedDataRequest) -> DerivedDataResponse:
        attributes = self._compute_attributes(request)
        risk_flags = self._evaluate_risk_flags(attributes)

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
        """Provisional attribute derivation from the request's own inputs.

        NOT real GST/bank-statement computation — that requires live AA
        integration, which is still unimplemented outside sandbox mode
        (see libs/integrations/factory.py::get_aa_client). This derives
        *some* signal from invoice_amount/gst_returns_months so every
        risk-flag threshold below is actually reachable by varying inputs,
        rather than the fixed constants this replaced. Replace with real
        GST-return/bank-statement/trade-history computation once AA/GST
        data flows are wired in.
        """
        months = request.gst_returns_months

        dso_days = max(20, 100 - months * 5)
        dpo_days = max(15, 60 - months * 2)
        ccc_days = dso_days - dpo_days

        # Larger single-invoice amounts relative to a 10-lakh baseline
        # suggest higher concentration risk on this one anchor relationship.
        revenue_concentration = min(
            Decimal("95"),
            Decimal("20") + (request.invoice_amount / Decimal("1000000")) * Decimal("15"),
        )
        dilution_rate = min(Decimal("30"), Decimal("2") * Decimal(12) / max(months, 1))
        anchor_avg_dpd = max(0, 45 - months * 3)
        anchor_payment_history_score = Decimal(100) - Decimal(anchor_avg_dpd)
        gst_compliance_score = min(Decimal("100"), Decimal("60") + Decimal(months) * Decimal("3"))

        return DerivedAttributes(
            dso_days=dso_days,
            dpo_days=dpo_days,
            ccc_days=ccc_days,
            revenue_concentration=revenue_concentration,
            dilution_rate=dilution_rate,
            anchor_payment_history_score=anchor_payment_history_score,
            anchor_avg_dpd=anchor_avg_dpd,
            gst_compliance_score=gst_compliance_score,
            vintage_months=months,
        )

    def _evaluate_risk_flags(self, attributes: DerivedAttributes) -> list[RiskFlag]:
        # revenue_concentration/dilution_rate are percentages (0-100) in the
        # API contract; the JDM ruleset expects fractions (0-1).
        context = {
            "revenue_concentration": float(attributes.revenue_concentration) / 100,
            "days_sales_outstanding": attributes.dso_days,
            "dilution_rate": float(attributes.dilution_rate) / 100,
            "anchor_avg_dpd": attributes.anchor_avg_dpd,
            "gst_compliance_score": float(attributes.gst_compliance_score),
            "vintage_months": attributes.vintage_months,
        }
        rows = self._engine.evaluate(_RULESET_NAME, context).output
        # collect hit-policy + multiple named outputs → list[dict], not a
        # single dict — see EvaluationResult.output's docstring.
        assert isinstance(rows, list), f"expected list output from {_RULESET_NAME}, got {type(rows)}"

        flags: list[RiskFlag] = []
        for row in rows:
            jdm_flag = row.get("flag")
            if not jdm_flag or jdm_flag == "none":
                continue
            code, description, threshold = _FLAG_META[jdm_flag]
            flags.append(
                RiskFlag(
                    flag_code=code,
                    severity=row.get("severity", "medium"),
                    description=description,
                    threshold=threshold,
                    actual_value=self._actual_value_for(jdm_flag, attributes),
                )
            )
        return flags

    @staticmethod
    def _actual_value_for(jdm_flag: str, attributes: DerivedAttributes) -> str:
        return {
            "high_concentration": f"{attributes.revenue_concentration}%",
            "elevated_dso": str(attributes.dso_days),
            "high_dilution": f"{attributes.dilution_rate}%",
            "anchor_payment_delays": str(attributes.anchor_avg_dpd),
            "low_gst_compliance": str(attributes.gst_compliance_score),
            "low_vintage": str(attributes.vintage_months),
        }[jdm_flag]
