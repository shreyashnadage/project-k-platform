"""Factory for creating integration clients — real or sandbox based on config.

The integration mode is controlled by the INTEGRATION_MODE environment variable:
  - "sandbox" → loads clients from the sandbox/ package (simulated responses)
  - "live"    → loads real client implementations

There is NO default. If INTEGRATION_MODE is not set, the application fails
at startup with a clear error. This prevents accidental sandbox usage in
production or silent failures from misconfiguration.

Usage:
    from libs.integrations.factory import get_aa_client, get_ocen_client

    aa = get_aa_client()  # Returns sandbox or real based on INTEGRATION_MODE
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.integrations.protocols import (
        AAClient,
        ConsentClient,
        GSTClient,
        LenderCallbackClient,
        OCENClient,
        UdyamClient,
    )


def _get_mode() -> str:
    mode = os.environ.get("INTEGRATION_MODE", "")
    if mode not in ("sandbox", "live"):
        msg = (
            f"INTEGRATION_MODE environment variable must be set to 'sandbox' or 'live'. "
            f"Got: {mode!r}. Set it in your .env file or deployment config."
        )
        raise RuntimeError(msg)
    return mode


def get_aa_client() -> AAClient:
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxAAClient

        return SandboxAAClient()
    raise NotImplementedError("Real AA client (Setu/Perfios) not yet implemented")


def get_ocen_client() -> OCENClient:
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxOCENClient

        return SandboxOCENClient()
    raise NotImplementedError("Real OCEN client not yet implemented")


def get_ocen_network_client() -> OcenNetworkClient:  # noqa: F821
    """Get the real OCEN network client (protocol-level, not mock interface)."""
    from libs.ocen_client.network_client import OcenNetworkClient

    return OcenNetworkClient()


def get_gst_client() -> GSTClient:
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxGSTClient

        return SandboxGSTClient()
    raise NotImplementedError("Real GST client not yet implemented")


def get_consent_client() -> ConsentClient:
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxConsentClient

        return SandboxConsentClient()
    from dpdp_core.consent.ledger import create_ledger

    return create_ledger()


def get_lender_client(auto_approve: bool = True) -> LenderCallbackClient:
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxLenderClient

        return SandboxLenderClient(auto_approve=auto_approve)
    raise NotImplementedError("Real lender callback client not yet implemented")


def get_udyam_client() -> UdyamClient:
    """Get Udyam verification client based on INTEGRATION_MODE and UDYAM_TSP_PROVIDER.

    Provider selection (only matters in live mode):
      UDYAM_TSP_PROVIDER=gridlines → Gridlines.io
      UDYAM_TSP_PROVIDER=surepass → Surepass.io
    """
    if _get_mode() == "sandbox":
        from ocen_sandbox import SandboxUdyamClient

        return SandboxUdyamClient()

    provider = os.environ.get("UDYAM_TSP_PROVIDER", "gridlines").lower()
    if provider == "gridlines":
        from libs.integrations.udyam import GridlinesUdyamClient

        return GridlinesUdyamClient()
    if provider == "surepass":
        from libs.integrations.udyam import SurepassUdyamClient

        return SurepassUdyamClient()

    msg = f"Unknown UDYAM_TSP_PROVIDER: {provider!r}. Use 'gridlines' or 'surepass'."
    raise RuntimeError(msg)


def get_db_session_factory():
    """Get an async session factory for database access."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from libs.db.engine import DATABASE_URL  # shared default + fail-fast guard

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def session_context():
        async with async_session() as session:
            yield session

    return session_context
