from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from account_kit.db import Base


async def init_db(engine: AsyncEngine) -> None:
    """Create the auth schema and account tables. Does not drop anything."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.run_sync(Base.metadata.create_all)
