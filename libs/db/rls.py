"""PostgreSQL Row-Level Security session setup.

Called by middleware after JWT verification to set the tenant context
on the database session. RLS policies then restrict queries to rows
belonging to the authenticated tenant.

Config-driven: reads tenancy.yaml for claim path, session variable name,
and bypass roles.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

TENANCY_CONFIG_PATH = os.environ.get("TENANCY_CONFIG_PATH", "tenancy.yaml")


@lru_cache(maxsize=1)
def _load_tenancy_config() -> dict[str, Any]:
    path = Path(TENANCY_CONFIG_PATH)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_tenant_claim_path() -> str:
    config = _load_tenancy_config()
    return config.get("tenant_claim_path", "org_id")


def get_session_variable() -> str:
    config = _load_tenancy_config()
    return config.get("session_variable", "app.tenant_id")


def get_bypass_roles() -> set[str]:
    config = _load_tenancy_config()
    return set(config.get("bypass_roles", []))


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Set the RLS tenant context for the current database session.

    Must be called after JWT verification extracts the tenant ID.
    Uses SET LOCAL so the setting is transaction-scoped — automatically
    cleared when the transaction ends.
    """
    variable = get_session_variable()
    await session.execute(
        f"SET LOCAL {variable} = :tenant_id",  # noqa: S608
        {"tenant_id": tenant_id},
    )


async def clear_tenant_context(session: AsyncSession) -> None:
    """Reset tenant context — for bypass roles that see all data."""
    variable = get_session_variable()
    await session.execute(f"RESET {variable}")


def should_bypass_rls(roles: set[str]) -> bool:
    """Check if the request's roles should bypass tenant isolation."""
    return bool(roles & get_bypass_roles())


def reset_tenancy_cache() -> None:
    """Clear cached config — for tests."""
    _load_tenancy_config.cache_clear()
