"""TSP adapter implementations for Udyam verification.

Each adapter normalizes the TSP-specific response into UdyamVerificationResult.
Switch between providers via UDYAM_TSP_PROVIDER env var or config.

Supported providers:
  - gridlines: Gridlines.io (sandbox + production)
  - surepass: Surepass.io (sandbox + production)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from libs.integrations.protocols import UdyamVerificationResult

logger = structlog.get_logger()


class GridlinesUdyamClient:
    """Gridlines.io Udyam verification adapter.

    Docs: https://docs.gridlines.io
    Sandbox base: https://sandbox.gridlines.io
    Production base: https://api.gridlines.io
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GRIDLINES_API_KEY", "")
        self._base_url = base_url or os.environ.get(
            "GRIDLINES_BASE_URL", "https://sandbox.gridlines.io"
        )

    async def verify(self, udyam_number: str) -> UdyamVerificationResult:
        log = logger.bind(provider="gridlines", udyam_number=udyam_number[:10] + "***")
        log.info("udyam_verification_request")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/udyam-aadhaar/udyam/verify",
                json={"udyam_number": udyam_number},
                headers={
                    "X-API-Key": self._api_key,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            log.warning("udyam_verification_failed", status=response.status_code)
            return UdyamVerificationResult(udyam_number=udyam_number, valid=False)

        data = response.json()
        result = data.get("data", {})

        return self._normalize(udyam_number, result, data)

    def _normalize(
        self, udyam_number: str, result: dict[str, Any], raw: dict[str, Any]
    ) -> UdyamVerificationResult:
        address_parts = result.get("official_address", {})
        address_str = ", ".join(
            filter(None, [
                address_parts.get("flat"),
                address_parts.get("building"),
                address_parts.get("street"),
                address_parts.get("city"),
                address_parts.get("district"),
                address_parts.get("state"),
                address_parts.get("pincode"),
            ])
        )

        nic_codes = [
            {"code": n.get("nic_2_digit", ""), "description": n.get("activity", "")}
            for n in result.get("nic_codes", [])
        ]

        return UdyamVerificationResult(
            udyam_number=udyam_number,
            valid=True,
            enterprise_name=result.get("enterprise_name"),
            enterprise_type=result.get("enterprise_type"),
            major_activity=result.get("major_activity"),
            organization_type=result.get("organization_type"),
            date_of_incorporation=result.get("date_of_incorporation"),
            date_of_commencement=result.get("date_of_commencement"),
            date_of_udyam_registration=result.get("date_of_udyam_registration"),
            state=address_parts.get("state"),
            district=address_parts.get("district"),
            city=address_parts.get("city"),
            pincode=address_parts.get("pincode"),
            address=address_str or None,
            nic_codes=nic_codes,
            owner_name=result.get("owner_name"),
            social_category=result.get("social_category"),
            dic=result.get("dic"),
            raw_response=raw,
        )


class SurepassUdyamClient:
    """Surepass.io Udyam verification adapter.

    Docs: https://docs.surepass.io
    Sandbox base: https://sandbox.surepass.io/api/v1
    Production base: https://kyc-api.surepass.io/api/v1
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("SUREPASS_API_KEY", "")
        self._base_url = base_url or os.environ.get(
            "SUREPASS_BASE_URL", "https://sandbox.surepass.io/api/v1"
        )

    async def verify(self, udyam_number: str) -> UdyamVerificationResult:
        log = logger.bind(provider="surepass", udyam_number=udyam_number[:10] + "***")
        log.info("udyam_verification_request")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/udyam/udyam",
                json={"id_number": udyam_number},
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            log.warning("udyam_verification_failed", status=response.status_code)
            return UdyamVerificationResult(udyam_number=udyam_number, valid=False)

        data = response.json()
        result = data.get("data", {})

        return self._normalize(udyam_number, result, data)

    def _normalize(
        self, udyam_number: str, result: dict[str, Any], raw: dict[str, Any]
    ) -> UdyamVerificationResult:
        nic_codes = [
            {"code": n.get("nic_code", ""), "description": n.get("activity", "")}
            for n in result.get("nic_code", []) if isinstance(n, dict)
        ]

        return UdyamVerificationResult(
            udyam_number=udyam_number,
            valid=result.get("status", "").lower() != "invalid",
            enterprise_name=result.get("enterprise_name") or result.get("name_of_enterprise"),
            enterprise_type=result.get("enterprise_type") or result.get("msme_type"),
            major_activity=result.get("major_activity"),
            organization_type=result.get("organisation_type"),
            date_of_incorporation=result.get("date_of_incorporation"),
            date_of_commencement=result.get("date_of_commencement"),
            date_of_udyam_registration=result.get("date_of_registration"),
            state=result.get("state"),
            district=result.get("district"),
            city=result.get("city"),
            pincode=result.get("pincode") or result.get("pin"),
            address=result.get("address") or result.get("flat_no"),
            nic_codes=nic_codes,
            owner_name=result.get("owner_name"),
            social_category=result.get("social_category"),
            dic=result.get("dic"),
            raw_response=raw,
        )
