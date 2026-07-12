"""Sandbox DPDP consent client — simulates consent ledger responses."""

from __future__ import annotations

import os

import structlog

from libs.integrations.protocols import ConsentCheckResult

logger = structlog.get_logger()


class SandboxConsentClient:
    """Sandbox consent client controlled by environment variables.

    By default, consent is granted for all purposes. Override with:
      DPDP_SANDBOX_CONSENT_DENIED=true  → all consent checks fail
      DPDP_SANDBOX_SCENARIO=consent_revoked_mid_flow → scenario-driven
    """

    def __init__(self) -> None:
        self._linked_consents: dict[str, str] = {}

    async def check_consent(
        self, data_principal_id: str, purposes: list[str]
    ) -> ConsentCheckResult:
        denied = os.environ.get("DPDP_SANDBOX_CONSENT_DENIED", "false").lower() == "true"

        if denied:
            logger.info(
                "sandbox_consent_denied",
                data_principal_id=data_principal_id,
                purposes=purposes,
            )
            return ConsentCheckResult(allowed=False, reason="consent_not_granted")

        logger.info(
            "sandbox_consent_granted",
            data_principal_id=data_principal_id,
            purposes=purposes,
        )
        return ConsentCheckResult(allowed=True, reason="sandbox_auto_grant")

    async def link_aa_consent(
        self, data_principal_id: str, aa_consent_id: str, loan_application_id: str
    ) -> None:
        self._linked_consents[loan_application_id] = aa_consent_id
        logger.info(
            "sandbox_aa_consent_linked",
            data_principal_id=data_principal_id,
            aa_consent_id=aa_consent_id,
            loan_application_id=loan_application_id,
        )
