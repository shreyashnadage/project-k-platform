"""Decision receipt signing and hash-chain construction.

Every rule evaluation (D0-D3) produces a DecisionReceipt.
This module:
1. Content-addresses the ruleset (SHA-256 of canonical JSON)
2. Content-addresses the input (SHA-256 of canonical JSON)
3. Signs the receipt with a KMS/HSM key (or local key for dev)
4. Chains receipts: h_n = SHA-256(receipt_bytes ‖ h_{n-1})

The signed, chained receipt is the DDP audit artifact — it proves
which rule version, applied to which input, produced which output,
and when, in a tamper-evident sequence.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel

from libs.common.models import DecisionGate, DecisionOutcome, DecisionReceipt


def canonical_json(data: dict[str, Any] | list | BaseModel) -> bytes:
    """Produce deterministic, sorted-key JSON bytes for hashing.
    Uses orjson for speed + deterministic output."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return orjson.dumps(data, option=orjson.OPT_SORT_KEYS)


def content_hash(data: dict[str, Any] | list | BaseModel) -> str:
    """SHA-256 of canonical JSON."""
    return hashlib.sha256(canonical_json(data)).hexdigest()


def hash_ruleset_file(ruleset_path: str) -> str:
    """SHA-256 of a JDM ruleset file (the GoRules JSON decision table)."""
    with open(ruleset_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class ReceiptSigner:
    """Signs decision receipts.

    In production, delegates to AWS KMS (asymmetric sign with RSA or ECC).
    In dev/test, uses a local HMAC key.

    Usage:
        signer = ReceiptSigner.from_env()
        receipt = signer.create_receipt(...)
    """

    def __init__(self, signing_key: bytes, mode: str = "hmac"):
        self._key = signing_key
        self._mode = mode

    @classmethod
    def from_env(cls) -> ReceiptSigner:
        """Load signing config from environment.
        TODO: In production, initialise a KMS client here."""
        import os

        key = os.environ.get("RECEIPT_SIGNING_KEY", "dev-signing-key-do-not-use-in-prod")
        return cls(signing_key=key.encode(), mode="hmac")

    def sign(self, data: bytes) -> str:
        """Sign bytes and return hex signature."""
        import hmac as hmac_mod

        if self._mode == "hmac":
            return hmac_mod.new(self._key, data, hashlib.sha256).hexdigest()
        # TODO: KMS mode — call boto3 kms.sign()
        raise NotImplementedError(f"Signing mode {self._mode} not implemented")

    def create_receipt(
        self,
        loan_application_id: UUID,
        gate: DecisionGate,
        outcome: DecisionOutcome,
        ruleset_hash: str,
        rule_input: dict[str, Any],
        rule_output: dict[str, Any],
        engine_version: str,
        previous_chain_hash: str | None = None,
    ) -> DecisionReceipt:
        """Create a signed, chain-linked decision receipt."""
        input_hash = content_hash(rule_input)

        receipt = DecisionReceipt(
            id=uuid4(),
            loan_application_id=loan_application_id,
            gate=gate,
            outcome=outcome,
            ruleset_hash=ruleset_hash,
            input_hash=input_hash,
            output=rule_output,
            engine_version=engine_version,
            evaluated_at=datetime.utcnow(),
        )

        # Sign the receipt
        receipt_bytes = canonical_json(receipt)
        receipt.signature = self.sign(receipt_bytes)

        # Chain: h_n = SHA-256(receipt_bytes ‖ h_{n-1})
        chain_input = receipt_bytes
        if previous_chain_hash:
            chain_input += previous_chain_hash.encode()
        receipt.chain_hash = hashlib.sha256(chain_input).hexdigest()

        return receipt


class ChainVerifier:
    """Verifies the integrity of a sequence of chained decision receipts."""

    @staticmethod
    def verify_chain(receipts: list[DecisionReceipt]) -> bool:
        """Verify that no receipt in the chain has been tampered with.
        Returns True if the chain is intact."""
        prev_hash: str | None = None
        for receipt in receipts:
            receipt_bytes = canonical_json(
                receipt.model_copy(update={"chain_hash": None, "signature": None})
            )
            chain_input = receipt_bytes
            if prev_hash:
                chain_input += prev_hash.encode()
            expected = hashlib.sha256(chain_input).hexdigest()
            if receipt.chain_hash != expected:
                return False
            prev_hash = receipt.chain_hash
        return True
