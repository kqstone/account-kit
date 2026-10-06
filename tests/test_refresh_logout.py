"""0.2.2 items 3-4: refresh tokens and logout."""

import pyotp
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from account_kit.models import User
from tests.helpers import approved_user, audit_events, bearer


async def _login(api, username, password="secret1", **extra):
    return await api["client"].post("/api/auth/login", data={"username": username, "password": password, **extra})


async def test_refresh_off_by_default(api):
    _u, body = await approved_user(api, "r0")
    assert set(body) == {"access_token", "token_type"}
    res = await api["client"].post("/api/auth/refresh", json={"refresh_token": "x"})
    assert res.status_code == 404


async def test_refresh_rotation_and_reuse_detection(api):
    api["config"].refresh_token_enabled = True
    user, body = await approved_user(api, "r1")
    assert body["refresh_token"] and body["refresh_expires_in"] == 30 * 86400
    client = api["client"]
    first = body["refresh_token"]
    rotated = await client.post("/api/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()["refresh_token"]
    assert second != first
    me = await client.get("/api/auth/me", headers=bearer(rotated.json()))
    assert me.status_code == 200
    # Reusing the rotated token revokes the family and ends the session.
    reused = await client.post("/api/auth/refresh", json={"refresh_token": first})
    assert reused.status_code == 401
    assert reused.json()["detail"]["code"] == "REFRESH_REUSED"
    dead = await client.post("/api/auth/refresh", json={"refresh_token": second})
    assert dead.status_code == 401
    assert dead.json()["detail"]["code"] == "REFRESH_INVALID"
    stale = await client.get("/api/auth/me", headers=bearer(rotated.json()))
    assert stale.status_code == 401  # single_device session cleared
    assert "refresh_reuse_detected" in await audit_events(api, user["id"])
    bogus = await client.post("/api/auth/refresh", json={"refresh_token": "nope"})
    assert bogus.json()["detail"]["code"] == "REFRESH_INVALID"


async def test_refresh_respects_single_device(api):
    api["config"].refresh_token_enabled = True
    _u, body = await approved_user(api, "r2")
    other = await _login(api, "r2", force="true", device_name="phone")
    assert other.status_code == 200
    res = await api["client"].post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert res.status_code == 401
    ok = await api["client"].post("/api/auth/refresh", json={"refresh_token": other.json()["refresh_token"]})
    assert ok.status_code == 200, ok.text


async def test_refresh_revoked_on_password_change_and_disable(api):
    config = api["config"]
    config.refresh_token_enabled = True
    user, body = await approved_user(api, "r3")
    client = api["client"]
    changed = await client.post(
        "/api/auth/change-password", json={"old_password": "secret1", "new_password": "secret2"}, headers=bearer(body)
    )
    assert changed.status_code == 200
    res = await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert res.status_code == 401
    fresh = (await _login(api, "r3", "secret2", force="true")).json()
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.is_active = False
        await db.commit()
    disabled = await client.post("/api/auth/refresh", json={"refresh_token": fresh["refresh_token"]})
    assert disabled.status_code == 403


async def test_refresh_issued_by_2fa_login_and_revoked_by_admin(api):
    config = api["config"]
    config.refresh_token_enabled = True
    user, body = await approved_user(api, "r4")
    client = api["client"]
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=bearer(body))
    totp = pyotp.TOTP(setup.json()["secret"])
    assert (await client.post("/api/auth/2fa/enable", json={"code": totp.now()}, headers=bearer(body))).status_code == 200
    challenge = (await _login(api, "r4", force="true")).json()["detail"]["challenge_token"]
    import time

    code = totp.at(time.time() + 30)
    done = await client.post("/api/auth/login/2fa", data={"challenge_token": challenge, "code": code, "force": "true"})
    assert done.status_code == 200, done.text
    assert done.json()["refresh_token"]
    # Admin 2FA reset revokes refresh tokens.
    _a, admin_body = await approved_user(api, "boss")
    async with api["sessions"]() as db:
        row = await db.get(User, _a["id"])
        row.is_admin = True
        await db.commit()
    reset = await client.post(f"/api/admin/account/users/{user['id']}/2fa/reset", headers=bearer(admin_body))
    assert reset.status_code == 204
    res = await client.post("/api/auth/refresh", json={"refresh_token": done.json()["refresh_token"]})
    assert res.status_code == 401
    assert "2fa_reset" in await audit_events(api, user["id"])


async def test_logout_clears_session_and_is_lenient(api):
    config = api["config"]
    config.refresh_token_enabled = True
    user, body = await approved_user(api, "lo1")
    client = api["client"]
    # No token / garbage token: still 200.
    assert (await client.post("/api/auth/logout")).json() == {"status": "success"}
    assert (await client.post("/api/auth/logout", headers=bearer("garbage"))).status_code == 200
    out = await client.post("/api/auth/logout", headers=bearer(body))
    assert out.status_code == 200
    # Session freed: another device logs in without force (dedd semantic).
    again = await _login(api, "lo1", device_name="phone")
    assert again.status_code == 200, again.text
    # Refresh tokens of the logged-out session are revoked.
    res = await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert res.status_code == 401
    # A stale token never clears the newer session.
    await client.post("/api/auth/logout", headers=bearer(body))
    me = await client.get("/api/auth/me", headers=bearer(again.json()))
    assert me.status_code == 200
    assert "logout" in await audit_events(api, user["id"])


async def test_logout_with_refresh_token_and_all_devices(api):
    config = api["config"]
    config.refresh_token_enabled = True
    config.session_mode = "stateless"
    _u, body = await approved_user(api, "lo2")
    second = (await _login(api, "lo2")).json()
    client = api["client"]
    out = await client.post("/api/auth/logout", json={"refresh_token": body["refresh_token"]})
    assert out.status_code == 200
    assert (await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]})).status_code == 200
    third = (await _login(api, "lo2")).json()
    everywhere = await client.post("/api/auth/logout", json={"all_devices": True}, headers=bearer(third))
    assert everywhere.status_code == 200
    assert (await client.post("/api/auth/refresh", json={"refresh_token": third["refresh_token"]})).status_code == 401


async def test_logout_path_configurable_and_disable(api):
    from account_kit import mount_account
    from account_kit.config import AccountKitConfig

    base = api["config"]

    async def get_db():
        async with api["sessions"]() as session:
            yield session

    app = FastAPI()
    mount_account(app, get_db, AccountKitConfig(jwt_secret="t", mailer=base.mailer, logout_path="/session/end"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/api/auth/session/end")).status_code == 200
        assert (await client.post("/api/auth/logout")).status_code in (404, 405)
    app2 = FastAPI()
    mount_account(app2, get_db, AccountKitConfig(jwt_secret="t", mailer=base.mailer, logout_enabled=False))
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://t") as client:
        assert (await client.post("/api/auth/logout")).status_code in (404, 405)
