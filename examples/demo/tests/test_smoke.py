"""Demo host smoke: setup wizard then kit auth flows against a real Postgres."""

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from server.app import create_app


async def _drop_auth(db):
    conn = await asyncpg.connect(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        database=db["database"],
        timeout=5,
    )
    try:
        await conn.execute("DROP SCHEMA IF EXISTS auth CASCADE")
    finally:
        await conn.close()


@pytest.fixture
async def demo(tmp_path, monkeypatch, db_parts):
    await _drop_auth(db_parts)
    cfg = tmp_path / ".demo-config.json"
    monkeypatch.setenv("DEMO_CONFIG_PATH", str(cfg))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {"client": client, "db": db_parts, "app": app, "config_path": cfg}
    runtime = app.state.runtime
    if runtime.engine is not None:
        await runtime.engine.dispose()


def _code(body):
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return detail.get("code")
    return None


async def test_setup_then_auth_smoke(demo):
    client = demo["client"]
    db = demo["db"]

    status = await client.get("/api/setup/status")
    assert status.status_code == 200, status.text
    assert status.json()["initialized"] is False

    probed = await client.post("/api/setup/test-db", json=db)
    assert probed.status_code == 200, probed.text
    assert probed.json() == {"ok": True}

    init = await client.post(
        "/api/setup/init",
        json={
            "db": db,
            "admin": {"username": "demo-admin", "email": "admin@example.com", "password": "secret1a"},
            "features": {
                "refresh": True,
                "captcha": True,
                "self_delete": True,
                "two_factor_email": True,
                "require_approval": False,
                "captcha_fail_threshold": 1,
            },
            "mail_mode": "console",
        },
    )
    assert init.status_code == 200, init.text
    body = init.json()
    assert body["initialized"] is True
    assert demo["config_path"].is_file()

    locked = await client.post(
        "/api/setup/init",
        json={
            "db": db,
            "admin": {"username": "demo-admin", "email": "admin@example.com", "password": "secret1a"},
            "mail_mode": "console",
        },
    )
    assert locked.status_code == 409
    assert _code(locked.json()) == "ALREADY_INITIALIZED"
    locked_db = await client.post("/api/setup/test-db", json=db)
    assert locked_db.status_code == 409

    ready = await client.get("/api/setup/status")
    assert ready.json()["initialized"] is True

    admin_login = await client.post(
        "/api/auth/login",
        data={"username": "demo-admin", "password": "secret1a"},
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_tokens = admin_login.json()
    assert admin_tokens.get("refresh_token")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}

    email = "user1@example.com"
    sent = await client.post(
        "/api/auth/send-code",
        json={"email": email, "purpose": "register", "language": "zh"},
    )
    assert sent.status_code == 200, sent.text
    box = await client.get("/api/demo/outbox", params={"email": email, "purpose": "register"})
    assert box.status_code == 200, box.text
    items = box.json()["items"]
    assert items and items[0]["code"]
    code = items[0]["code"]

    created = await client.post(
        "/api/auth/register",
        json={"username": "user1", "email": email, "password": "secret1", "code": code},
    )
    assert created.status_code == 200, created.text
    assert created.json()["username"] == "user1"

    logged = await client.post(
        "/api/auth/login",
        data={"username": "user1", "password": "secret1"},
    )
    assert logged.status_code == 200, logged.text
    tokens = logged.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    first_refresh = tokens["refresh_token"]
    user_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    rotated = await client.post("/api/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()["refresh_token"]
    assert second and second != first_refresh
    reused = await client.post("/api/auth/refresh", json={"refresh_token": first_refresh})
    assert reused.status_code == 401
    assert _code(reused.json()) == "REFRESH_REUSED"

    gate = None
    for _ in range(6):
        gate = await client.post("/api/auth/login", data={"username": "user1", "password": "nope"})
        if gate.status_code == 428:
            break
    assert gate is not None and gate.status_code == 428, gate.text if gate is not None else "no login"
    assert _code(gate.json()) == "CAPTCHA_REQUIRED"

    captcha = await client.get("/api/auth/captcha")
    assert captcha.status_code == 200, captcha.text
    image = captcha.json()
    assert image.get("captcha_id") and image.get("image_base64")

    deleted = await client.post(
        "/api/auth/me/delete",
        json={"password": "secret1"},
        headers=user_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "success"

    logs = await client.get("/api/admin/account/audit-logs", headers=admin_headers)
    assert logs.status_code == 200, logs.text
    events = [row["event"] for row in logs.json()["items"]]
    assert "login_success" in events
    assert "account_deleted" in events

    out = await client.post("/api/auth/logout", headers=admin_headers)
    assert out.status_code == 200, out.text
    assert out.json()["status"] == "success"
