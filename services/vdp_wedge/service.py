"""VDP Wedge service — invoice ingestion and Kind 1 attestation logic."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from libs.common.events import invoice_kind1_attested

from .models import (
    InvoiceIngestionRequest,
    InvoiceIngestionResponse,
    Kind1CheckResponse,
)

if TYPE_CHECKING:
    from libs.zen_rules.engine import ZenDecisionEngine

logger = structlog.get_logger()

IRN_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class VDPWedgeService:
    """Handles invoice ingestion and Kind 1 attestation checks."""

    def __init__(self, zen_engine: ZenDecisionEngine) -> None:
        self._zen = zen_engine
        self._invoices: dict[uuid.UUID, dict[str, Any]] = {}

    def ingest_invoice(self, request: InvoiceIngestionRequest) -> InvoiceIngestionResponse:
        invoice_id = uuid.uuid4()
        irn_valid = bool(IRN_PATTERN.match(request.irn))

        invoice_data = {
            "id": invoice_id,
            "irn": request.irn,
            "irn_valid": irn_valid,
            "anchor_gstin": request.anchor_gstin,
            "vendor_gstin": request.vendor_gstin,
            "amount": request.amount,
            "currency": request.currency,
            "issue_date": request.issue_date,
            "due_date": request.due_date,
            "ims_status": request.ims_status,
            "repayment_routing_active": request.repayment_routing_active,
            "gstin_valid": len(request.vendor_gstin) == 15,
        }
        self._invoices[invoice_id] = invoice_data

        kind1_outcome = None
        kind1_reason = None
        kind1_eligible = False

        if (
            irn_valid
            and request.ims_status in ("accepted", "deemed_accepted")
            and request.repayment_routing_active
        ):
            result = self._evaluate_kind1(invoice_data)
            kind1_outcome = result.output.get("outcome")
            kind1_reason = result.output.get("reason")
            kind1_eligible = kind1_outcome == "pass"

        logger.info(
            "invoice_ingested",
            invoice_id=str(invoice_id),
            irn_valid=irn_valid,
            kind1_eligible=kind1_eligible,
        )

        return InvoiceIngestionResponse(
            invoice_id=invoice_id,
            irn=request.irn,
            irn_valid=irn_valid,
            ims_status=request.ims_status,
            kind1_eligible=kind1_eligible,
            kind1_outcome=kind1_outcome,
            kind1_reason=kind1_reason,
        )

    def check_kind1(self, invoice_id: uuid.UUID) -> Kind1CheckResponse:
        invoice_data = self._invoices.get(invoice_id)
        if not invoice_data:
            raise KeyError(f"Invoice {invoice_id} not found")

        result = self._evaluate_kind1(invoice_data)

        if result.output.get("outcome") == "pass":
            invoice_kind1_attested(
                invoice_id=invoice_id,
                loan_application_id=invoice_id,  # placeholder until loan app created
                irn=invoice_data["irn"],
                ims_status=invoice_data["ims_status"],
                repayment_routing_active=invoice_data["repayment_routing_active"],
                is_kind1=True,
            )

        return Kind1CheckResponse(
            invoice_id=invoice_id,
            outcome=result.output.get("outcome", "error"),
            reason=result.output.get("reason", "evaluation_error"),
            ruleset_hash=result.ruleset_hash,
        )

    def _evaluate_kind1(self, invoice_data: dict[str, Any]):
        context = {
            "irn_valid": invoice_data["irn_valid"],
            "ims_status": invoice_data["ims_status"],
            "repayment_routing_active": invoice_data["repayment_routing_active"],
            "gstin_valid": invoice_data["gstin_valid"],
        }
        return self._zen.evaluate("d0-kind1-gate", context)
