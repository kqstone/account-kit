import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from account_kit.db import Base

logger = logging.getLogger("account_kit.schema")


def _warn_multiple_admins(count: int) -> None:
    logger.warning(
        "account-kit: skip unique index uq_users_single_admin (%s admin rows). "
        "Keep exactly one is_admin=true, then CREATE UNIQUE INDEX uq_users_single_admin "
        "ON auth.users (is_admin) WHERE is_admin = true.",
        count,
    )


async def _ensure_single_admin_index_async(conn) -> None:
    exists = await conn.scalar(text("SELECT to_regclass('auth.users')"))
    if not exists:
        return
    count = await conn.scalar(text("SELECT count(*) FROM auth.users WHERE is_admin = true"))
    if int(count or 0) > 1:
        _warn_multiple_admins(int(count))
        return
    await conn.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_admin ON auth.users (is_admin) WHERE is_admin = true")
    )


def _ensure_single_admin_index_sync(conn) -> None:
    exists = conn.execute(text("SELECT to_regclass('auth.users')")).scalar()
    if not exists:
        return
    count = conn.execute(text("SELECT count(*) FROM auth.users WHERE is_admin = true")).scalar()
    if int(count or 0) > 1:
        _warn_multiple_admins(int(count))
        return
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_admin ON auth.users (is_admin) WHERE is_admin = true"))


async def init_db(engine: AsyncEngine) -> None:
    """Create the auth schema and account tables. Does not drop anything."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_single_admin_index_async(conn)


async def ensure_schema(engine: AsyncEngine) -> None:
    """Idempotent upgrade helper for hosts without Alembic: creates the schema,
    any missing kit tables, and the single-admin unique index (skipped with a
    warning if more than one admin already exists). Safe to run on every start.
    Equivalent SQL: account_kit/sql/upgrade_0_2_2.sql then upgrade_0_2_3.sql."""
    await init_db(engine)


def ensure_schema_sync(engine) -> None:
    """Same as :func:`ensure_schema` for a synchronous SQLAlchemy engine."""
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        Base.metadata.create_all(bind=conn)
        _ensure_single_admin_index_sync(conn)


def upgrade_sql(version: str = "0.2.3") -> str:
    """Idempotent upgrade SQL shipped with the package (for host migrations)."""
    import os

    name = "upgrade_" + version.replace(".", "_") + ".sql"
    path = os.path.join(os.path.dirname(__file__), "sql", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()
