from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from account_kit.db import Base


async def init_db(engine: AsyncEngine) -> None:
    """Create the auth schema and account tables. Does not drop anything."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.run_sync(Base.metadata.create_all)


async def ensure_schema(engine: AsyncEngine) -> None:
    """Idempotent upgrade helper for hosts without Alembic: creates the schema and
    any missing kit tables (0.2.2 only adds tables, no column changes). Safe to
    run on every start. Equivalent SQL: account_kit/sql/upgrade_0_2_2.sql."""
    await init_db(engine)


def ensure_schema_sync(engine) -> None:
    """Same as :func:`ensure_schema` for a synchronous SQLAlchemy engine."""
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        Base.metadata.create_all(bind=conn)


def upgrade_sql(version: str = "0.2.2") -> str:
    """Idempotent upgrade SQL shipped with the package (for host migrations)."""
    import os

    name = "upgrade_" + version.replace(".", "_") + ".sql"
    path = os.path.join(os.path.dirname(__file__), "sql", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()
