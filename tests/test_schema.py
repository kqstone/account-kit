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


async def _index_exists(conn, name="uq_users_single_admin"):
    return await conn.scalar(
        text("SELECT 1 FROM pg_indexes WHERE schemaname = 'auth' AND indexname = :n"),
        {"n": name},
    )


async def test_migration_skips_index_when_two_admins():
    """Already-multiple admins: ensure_schema / upgrade_0_2_3 skip the unique index."""
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from account_kit import ensure_schema, seed_defaults
    from account_kit.models import User
    from account_kit.schema_setup import upgrade_sql
    from account_kit.security import hash_password
    from account_kit.seed import default_role

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)
        async with engine.begin() as conn:
            assert await _index_exists(conn) == 1
            await conn.execute(text("DROP INDEX IF EXISTS auth.uq_users_single_admin"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            await seed_defaults(db)
            role = await default_role(db)
            now = datetime.now(timezone.utc)
            for name in ("a1", "a2"):
                db.add(
                    User(
                        username=name,
                        email=f"{name}@example.com",
                        hashed_password=hash_password("secret1"),
                        role=role.code,
                        is_admin=True,
                        is_active=True,
                        approval_status="approved",
                        approved_at=now,
                    )
                )
            await db.commit()
        await ensure_schema(engine)
        sql = upgrade_sql("0.2.3")
        async with engine.connect() as conn:
            raw = await conn.get_raw_connection()
            await raw.driver_connection.execute(sql)
        async with engine.connect() as conn:
            assert await _index_exists(conn) is None
            count = await conn.scalar(text("SELECT count(*) FROM auth.users WHERE is_admin = true"))
            assert int(count) == 2
    finally:
        await engine.dispose()


async def test_upgrade_0_2_3_is_idempotent_with_one_admin():
    from account_kit import ensure_schema
    from account_kit.schema_setup import upgrade_sql

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)
        async with engine.begin() as conn:
            await conn.execute(text("DROP INDEX IF EXISTS auth.uq_users_single_admin"))
        sql = upgrade_sql("0.2.3")
        for _ in range(2):
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(sql)
        async with engine.connect() as conn:
            assert await _index_exists(conn) == 1
    finally:
        await engine.dispose()
