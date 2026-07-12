"""Sandbox DSR client — simulates Data Subject Rights fulfillment responses.

Responses driven by DPDP_SANDBOX_SCENARIO or environment variables.
"""

from __future__ import annotations

import os
from typing import Any


class SandboxDSRClient:
    """Mock DSR fulfillment client for sandbox/test environments."""

    async def execute_access(self, data_principal_id: str) -> dict[str, Any]:
        from sandbox.scenarios.loader import get_active_scenario

        scenario = get_active_scenario()
        if scenario:
            response = scenario.next_response("access_request")
            if response:
                return response

        return {
            "status": "fulfilled",
            "data": {
                "source": "sandbox",
                "vendor": {
                    "name": "Sandbox Vendor",
                    "gstin": data_principal_id,
                    "udyam_number": "UDYAM-MH-01-0000001",
                },
                "loan_applications": [],
                "consents": [{"purpose": "loan_origination", "granted": True}],
            },
        }

    async def execute_erasure(self, data_principal_id: str) -> dict[str, Any]:
        from sandbox.scenarios.loader import get_active_scenario

        scenario = get_active_scenario()
        if scenario:
            response = scenario.next_response("erasure_request")
            if response:
                return response

        legal_hold = os.environ.get("DPDP_SANDBOX_LEGAL_HOLD", "false").lower() == "true"

        if legal_hold:
            return {
                "status": "held",
                "result": {
                    "source": "sandbox",
                    "erased": False,
                    "skipped_reason": "legal_hold_active",
                },
            }

        return {
            "status": "fulfilled",
            "result": {
                "source": "sandbox",
                "erased": True,
                "pseudonymized_fields": ["name", "gstin", "udyam_number"],
            },
        }

    async def execute_correction(self, data_principal_id: str) -> dict[str, Any]:
        return {
            "status": "pending_review",
            "reason": "correction_requires_manual_verification",
        }
