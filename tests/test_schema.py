from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import account_kit.models  # noqa: F401
from account_kit.db import Base
from tests.conftest import _database_url


async def test_create_all_creates_auth_schema():
    """Hosts that call ``Base.metadata.create_all`` directly (no init_db) on an empty DB."""
    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.connect() as conn:
            found = await conn.scalar(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users'")
            )
        assert found == 1
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


NEW_TABLES = ("rate_limit_counters", "two_factor_challenges", "refresh_tokens", "captcha_challenges")


async def _columns(conn, table):
    rows = await conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'auth' AND table_name = :t ORDER BY column_name"
        ),
        {"t": table},
    )
    return [tuple(row) for row in rows]


async def test_upgrade_sql_is_idempotent_and_matches_models():
    """0.2.1 database (new tables missing) + upgrade SQL twice == create_all."""
    from account_kit import ensure_schema
    from account_kit.schema_setup import upgrade_sql

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)
        async with engine.connect() as conn:
            expected = {table: await _columns(conn, table) for table in NEW_TABLES}
        async with engine.begin() as conn:
            for table in NEW_TABLES:
                await conn.execute(text(f"DROP TABLE auth.{table}"))
        sql = upgrade_sql("0.2.2")
        for _ in range(2):
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(sql)  # asyncpg: multi-statement script
        async with engine.connect() as conn:
            for table in NEW_TABLES:
                assert await _columns(conn, table) == expected[table], table
        # ensure_schema on an already-upgraded database is a no-op.
        await ensure_schema(engine)
    finally:
        await engine.dispose()
