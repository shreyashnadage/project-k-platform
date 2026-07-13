"""Root test configuration."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("INTEGRATION_MODE", "sandbox")
os.environ.setdefault("GATEWAY_USE_DB", "false")


@pytest.fixture
async def real_db_session():
    """A real async DB session against DATABASE_URL, tables created fresh
    from libs/db/models.py's current SQLAlchemy models (not via Alembic —
    see migrations/versions/006_vendor_invite_tracking.py's docstring for
    why the 004/005 migration chain currently can't be run in sequence).

    Only for @pytest.mark.integration tests — requires `make up` (real
    Postgres). Truncates the tables it created after each test.
    """
    from libs.db.engine import async_session, engine
    from libs.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
def mock_db_session():
    """A mocked AsyncSession for tests that exercise DB-touching code paths
    without a real Postgres — matches tests/test_rls.py's existing
    AsyncMock() style. Use for the non-integration variant of a DB test.
    """
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session
