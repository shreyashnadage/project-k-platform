"""Backfill encrypted PII columns from existing plaintext.

Phase 2 of the zero-downtime encryption migration:
  - Reads plaintext values in batches
  - Encrypts via EncryptedString and computes BlindIndex
  - Writes to _enc/_idx columns
  - Verifiable: SELECT count(*) WHERE _enc IS NULL after completion should be 0

Run with: alembic upgrade 003
Rollback: alembic downgrade 002 (encrypted columns become NULL again)

Revision ID: 003
Revises: 002
Create Date: 2026-07-12
"""

from __future__ import annotations

import os

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

revision: str = "003"
down_revision: str = "002"
branch_labels: str | None = None
depends_on: str | None = None

BATCH_SIZE = 1000


def _get_encryption_key() -> bytes:
    key_hex = os.environ.get("DPDP_ENCRYPTION_KEY", "")
    if not key_hex:
        msg = "DPDP_ENCRYPTION_KEY must be set for backfill migration"
        raise RuntimeError(msg)
    return bytes.fromhex(key_hex)


def _encrypt_value(plaintext: str, key: bytes) -> bytes:
    """AES-256-GCM encrypt a plaintext value."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Format: version(1) + nonce(12) + ciphertext
    return b"\x01" + nonce + ciphertext


def _compute_blind_index(value: str, field_name: str) -> str:
    """HMAC-SHA256 blind index with domain separation."""
    import hashlib
    import hmac

    key_hex = os.environ.get("DPDP_BLIND_INDEX_KEY", "")
    if not key_hex:
        msg = "DPDP_BLIND_INDEX_KEY must be set for backfill migration"
        raise RuntimeError(msg)
    key = bytes.fromhex(key_hex)
    domain_key = hashlib.sha256(key + field_name.encode()).digest()
    return hmac.HMAC(domain_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _backfill_table(
    session: Session,
    table: str,
    columns: list[tuple[str, str, bool]],
    key: bytes,
) -> None:
    """Backfill encrypted columns for a table.

    columns: list of (plaintext_col, field_name_for_blind_index, has_blind_index)
    """
    offset = 0
    while True:
        col_list = ", ".join(c[0] for c in columns)
        query = f"SELECT id, {col_list} FROM {table} ORDER BY id LIMIT :limit OFFSET :offset"
        rows = session.execute(text(query), {"limit": BATCH_SIZE, "offset": offset}).fetchall()

        if not rows:
            break

        for row in rows:
            row_id = row[0]
            updates = {}
            params = {"row_id": row_id}

            for i, (col_name, field_name, has_idx) in enumerate(columns):
                value = row[i + 1]
                if value is None:
                    continue
                enc_col = f"{col_name}_enc"
                updates[enc_col] = f":{enc_col}"
                params[enc_col] = _encrypt_value(value, key)

                if has_idx:
                    idx_col = f"{col_name}_idx"
                    updates[idx_col] = f":{idx_col}"
                    params[idx_col] = _compute_blind_index(value, field_name)

            if updates:
                set_clause = ", ".join(f"{k} = {v}" for k, v in updates.items())
                session.execute(
                    text(f"UPDATE {table} SET {set_clause} WHERE id = :row_id"),
                    params,
                )

        session.commit()
        offset += BATCH_SIZE


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    key = _get_encryption_key()

    _backfill_table(session, "anchors", [
        ("name", "anchor_name", False),
        ("gstin", "anchor_gstin", True),
    ], key)

    _backfill_table(session, "vendors", [
        ("name", "vendor_name", False),
        ("gstin", "vendor_gstin", True),
        ("udyam_number", "vendor_udyam", True),
    ], key)

    _backfill_table(session, "loan_applications", [
        ("vendor_gstin", "loan_vendor_gstin", True),
        ("anchor_gstin", "loan_anchor_gstin", True),
    ], key)

    session.close()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute(text("UPDATE anchors SET name_enc = NULL, gstin_enc = NULL, gstin_idx = NULL"))
    session.execute(text(
        "UPDATE vendors SET name_enc = NULL, gstin_enc = NULL, gstin_idx = NULL, "
        "udyam_number_enc = NULL, udyam_number_idx = NULL"
    ))
    session.execute(text(
        "UPDATE loan_applications SET vendor_gstin_enc = NULL, vendor_gstin_idx = NULL, "
        "anchor_gstin_enc = NULL, anchor_gstin_idx = NULL"
    ))
    session.commit()
    session.close()
