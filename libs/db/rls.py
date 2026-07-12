"""PostgreSQL Row-Level Security session setup.

Called as a FastAPI dependency (tenant_scoped_session) after JWT
verification. RLS policies then restrict queries to rows belonging to the
authenticated tenant — enforced at the database level, so an application
bug cannot leak cross-tenant data.

Config-driven: reads tenancy.yaml for claim path, session variable name,
and bypass roles.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db.engine import get_session

# Set by DPDPRBACMiddleware after successful token verification; read by
# tenant_scoped_session() to decide what to set on the DB session.
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
resolved_roles_var: ContextVar[frozenset[str]] = ContextVar("resolved_roles", default=frozenset())


@lru_cache(maxsize=1)
def _load_tenancy_config() -> dict[str, Any]:
    # Read the env var here (not a frozen module-level constant) so tests
    # can override it via monkeypatch/os.environ before the first call —
    # the lru_cache still avoids re-reading the file on every subsequent
    # call within the same config generation.
    config_path = os.environ.get("TENANCY_CONFIG_PATH", "tenancy.yaml")
    path = Path(config_path)
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

    Uses set_config(..., is_local=true) rather than a raw `SET LOCAL`
    string: PostgreSQL's SET/SET LOCAL statements don't accept bind
    parameters over the extended query protocol (asyncpg included), so a
    literal-interpolated `SET LOCAL {var} = '{value}'` would either fail or
    require manual SQL-injection-safe escaping. set_config() is a regular
    function call — bind parameters work normally, and is_local=true gives
    the same transaction-scoped behavior as SET LOCAL (automatically
    cleared when the transaction ends).
    """
    variable = get_session_variable()
    await session.execute(
        text("SELECT set_config(:variable, :tenant_id, true)"),
        {"variable": variable, "tenant_id": tenant_id},
    )


RLS_BYPASS_SENTINEL = "__RLS_BYPASS__"


async def clear_tenant_context(session: AsyncSession) -> None:
    """Mark this session as bypassing tenant isolation (sees all data).

    Sets the session variable to a sentinel value, not an empty string.
    RLS policies check for this sentinel explicitly (see
    tenancy.yaml's rls_policy_template) — an empty string would make
    `tenant_column = current_setting(...)` match nothing, hiding all rows
    from bypass roles instead of showing everything.
    """
    variable = get_session_variable()
    await session.execute(
        text("SELECT set_config(:variable, :sentinel, true)"),
        {"variable": variable, "sentinel": RLS_BYPASS_SENTINEL},
    )


def should_bypass_rls(roles: set[str]) -> bool:
    """Check if the request's roles should bypass tenant isolation."""
    return bool(roles & get_bypass_roles())


async def tenant_scoped_session():
    """FastAPI dependency: yields a DB session with RLS tenant context set.

    Reads tenant_id_var / resolved_roles_var, populated by DPDPRBACMiddleware
    after successful token verification. Bypass-role requests (platform-admin,
    operations) get an unscoped session; everyone else gets `app.tenant_id`
    set to their org_id claim before any query runs.

    If no tenant_id was resolved at all (e.g. DPDP_RBAC_ENABLED=false in local
    dev, so the middleware never ran token verification), no RLS restriction
    is applied — this dependency never turns an unauthenticated dev request
    into an empty-tenant, everything-filtered-out session.
    """
    roles = resolved_roles_var.get()
    tenant_id = tenant_id_var.get()

    async for session in get_session():
        if tenant_id is None:
            yield session
        elif should_bypass_rls(set(roles)):
            await clear_tenant_context(session)
            yield session
        else:
            await set_tenant_context(session, tenant_id)
            yield session


def reset_tenancy_cache() -> None:
    """Clear cached config — for tests."""
    _load_tenancy_config.cache_clear()
