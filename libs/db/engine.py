"""Async SQLAlchemy engine and session factory.

DEFAULT_DATABASE_URL is the canonical dev-only fallback — reused by
libs/integrations/factory.py's get_db_session_factory() so the two call
sites can't silently point at different databases if DATABASE_URL isn't
set. Outside INTEGRATION_MODE=sandbox, using the default fails fast rather
than silently connecting to a local dev database with a known credential.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DATABASE_URL = "postgresql+asyncpg://ocen:ocen_dev@localhost:5432/ocen_platform"

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

if DATABASE_URL == DEFAULT_DATABASE_URL and os.environ.get("INTEGRATION_MODE", "") != "sandbox":
    raise RuntimeError(
        "DATABASE_URL is not set, and the dev-only default "
        f"({DEFAULT_DATABASE_URL!r}) would be used outside "
        "INTEGRATION_MODE=sandbox. Set DATABASE_URL explicitly for "
        "staging/production, or set INTEGRATION_MODE=sandbox for local "
        "development."
    )

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
