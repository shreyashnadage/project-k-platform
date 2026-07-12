"""Sandbox-specific configuration.

Controls mock behavior: response delays, approval rates, seed data scenarios.
These are tunable without touching the main framework.
"""

import os

SANDBOX_RESPONSE_DELAY_MS = int(os.environ.get("SANDBOX_RESPONSE_DELAY_MS", "0"))

SANDBOX_AA_AUTO_APPROVE = os.environ.get("SANDBOX_AA_AUTO_APPROVE", "true").lower() in (
    "true",
    "1",
)

SANDBOX_LENDER_AUTO_APPROVE = os.environ.get("SANDBOX_LENDER_AUTO_APPROVE", "true").lower() in (
    "true",
    "1",
)

SANDBOX_LENDER_MAX_AMOUNT = os.environ.get("SANDBOX_LENDER_MAX_AMOUNT", "1000000.00")
SANDBOX_LENDER_INTEREST_RATE = os.environ.get("SANDBOX_LENDER_INTEREST_RATE", "14.5")
SANDBOX_LENDER_TENURE_DAYS = int(os.environ.get("SANDBOX_LENDER_TENURE_DAYS", "90"))
