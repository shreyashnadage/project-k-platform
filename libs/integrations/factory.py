"""Factory for creating integration clients — real or mock based on config.

Usage:
    from libs.integrations.factory import get_aa_client, get_ocen_client

    aa = get_aa_client()  # Returns mock or real based on OCEN_USE_MOCKS env var
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.integrations.protocols import AAClient, GSTClient, LenderCallbackClient, OCENClient


def _use_mocks() -> bool:
    return os.environ.get("OCEN_USE_MOCKS", "true").lower() in ("true", "1", "yes")


def get_aa_client() -> AAClient:
    if _use_mocks():
        from libs.mocks.aa_client import MockAAClient

        return MockAAClient()
    raise NotImplementedError("Real AA client (Setu/Perfios) not yet implemented")


def get_ocen_client() -> OCENClient:
    if _use_mocks():
        from libs.mocks.ocen_client import MockOCENClient

        return MockOCENClient()
    raise NotImplementedError("Real OCEN client not yet implemented")


def get_gst_client() -> GSTClient:
    if _use_mocks():
        from libs.mocks.gst_client import MockGSTClient

        return MockGSTClient()
    raise NotImplementedError("Real GST client not yet implemented")


def get_lender_client(auto_approve: bool = True) -> LenderCallbackClient:
    if _use_mocks():
        from libs.mocks.lender_client import MockLenderCallbackClient

        return MockLenderCallbackClient(auto_approve=auto_approve)
    raise NotImplementedError("Real lender callback client not yet implemented")
