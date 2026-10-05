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
