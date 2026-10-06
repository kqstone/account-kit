import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from account_kit import init_db, mount_account
from account_kit.captcha import login_fail_tracker
from account_kit.captcha_image import memory_store as captcha_memory
from account_kit.state import memory_counters
from account_kit.config import AccountKitConfig
from account_kit.two_factor.challenges import challenge_store


def _database_url() -> str:
    url = os.environ.get("ACCOUNT_KIT_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("ACCOUNT_KIT_TEST_DATABASE_URL is not set")
    return url


@pytest.fixture
async def api():
    engine = create_async_engine(_database_url())
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
    await init_db(engine)
    login_fail_tracker.clear_all()
    challenge_store._items.clear()
    memory_counters.clear_all()
    captcha_memory.clear()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sent = []

    async def mailer(to, purpose, code, language):
        sent.append({"to": to, "purpose": purpose, "code": code, "language": language})

    async def get_db():
        async with sessions() as session:
            yield session

    config = AccountKitConfig(
        jwt_secret="test-secret",
        mailer=mailer,
        brand_name="Test",
        session_mode="single_device",
        require_approval=True,
        role_change_enabled=True,
        state_backend=os.environ.get("ACCOUNT_KIT_TEST_STATE_BACKEND", "db"),
    )
    app = FastAPI()
    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {"client": client, "sent": sent, "sessions": sessions, "config": config, "app": app}
    await engine.dispose()
