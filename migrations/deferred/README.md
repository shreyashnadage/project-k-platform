# Deferred migrations

Migrations here are **not** part of the active alembic chain
(`migrations/versions/`) and will not run via `alembic upgrade head`.
They're kept for reference — as a starting point for finishing the work
they describe — not as history of something already shipped.

## `004_drop_plaintext_columns.py.deferred`

Phase 3 of the zero-downtime PII encryption migration: drop the
plaintext `name`/`gstin`/`vendor_gstin`/`anchor_gstin`/`udyam_number`
columns on `anchors`/`vendors`/`loan_applications` and promote the
`_enc`/`_idx` columns (added by migration 002, backfilled by 003) to be
the columns of record.

**Why it's deferred, not just next in line:** its own docstring lists
"application code updated to read from `_enc` columns (dual-read phase
complete)" as a prerequisite. That prerequisite was never met —
`libs/db/models.py`, `libs/db/data_source.py`, and
`services/borrower_gateway/ops_api.py` all still read and write the
plaintext columns this migration drops. Running it today would break
every one of those call sites immediately (`column does not exist`).

Originally migration 005 (RLS) chained after this one, which meant the
two migrations produced divergent, unmergeable alembic heads the moment
005 was added — nothing ever chained past both of them, so
`alembic heads` reported two heads (`005` and whatever chained off `003`)
instead of one. 005 has since been re-parented to depend on `003`
directly, since RLS tenant isolation is an independent concern from this
encryption cutover and 005's policies already target the live plaintext
`anchor_gstin` column.

**To resurrect this migration:**
1. Design and implement real field-level encryption + blind-indexing on
   write (`libs/common/models.py`'s DPDP field types already exist for
   this — they're just not wired into the SQLAlchemy read/write paths).
2. Cut every read/write call site over to the `_enc`/`_idx` columns.
3. Verify with a real backfill + dual-read window in a non-prod
   environment.
4. Re-add this file to `migrations/versions/`, retarget its
   `down_revision` at whatever the chain's current head is by then, and
   update `libs/db/models.py` to match the post-migration schema in the
   same change (not a follow-up — that's exactly the gap that caused
   this file to be deferred in the first place).
