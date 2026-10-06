"""0.2.2 items 5-7, 9: self-delete, audit log, built-in captcha, DB-backed state."""

import time

import pyotp
import pytest
from sqlalchemy import func, select, text

from account_kit.models import RateLimitCounter, User
from tests.helpers import approved_user, audit_events, bearer


async def _make_admin(api, username="admin1"):
    user, body = await approved_user(api, username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.is_admin = True
        await db.commit()
    return user, bearer(body)


async def test_self_delete_disabled_by_default(api):
    _u, body = await approved_user(api, "d0")
    res = await api["client"].post("/api/auth/me/delete", json={"password": "secret1"}, headers=bearer(body))
    assert res.status_code == 404


async def test_self_delete_hard(api):
    config = api["config"]
    config.self_delete_enabled = True
    deleted = []

    async def on_deleted(db, user):
        deleted.append(user.username)

    config.on_deleted = on_deleted
    user, body = await approved_user(api, "d1")
    client = api["client"]
    bad = await client.post("/api/auth/me/delete", json={"password": "nope"}, headers=bearer(body))
    assert bad.status_code == 400
    ok = await client.request("DELETE", "/api/auth/me", json={"password": "secret1"}, headers=bearer(body))
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"status": "success", "mode": "hard"}
    assert deleted == ["d1"]
    async with api["sessions"]() as db:
        assert await db.get(User, user["id"]) is None
    assert "account_deleted" in await audit_events(api, user["id"])
    gone = await client.get("/api/auth/me", headers=bearer(body))
    assert gone.status_code == 401


async def test_self_delete_soft_with_2fa(api):
    config = api["config"]
    config.self_delete_enabled = True
    config.user_delete_mode = "soft"
    config.refresh_token_enabled = True
    user, body = await approved_user(api, "d2")
    client = api["client"]
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=bearer(body))
    totp = pyotp.TOTP(setup.json()["secret"])
    await client.post("/api/auth/2fa/enable", json={"code": totp.now()}, headers=bearer(body))
    need = await client.post("/api/auth/me/delete", json={"password": "secret1"}, headers=bearer(body))
    assert need.status_code == 400
    assert need.json()["detail"]["code"] == "MFA_CODE_REQUIRED"
    ok = await client.post(
        "/api/auth/me/delete", json={"password": "secret1", "code": totp.at(time.time() + 30)}, headers=bearer(body)
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["mode"] == "soft"
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        assert row is not None and row.is_active is False
        assert row.username.startswith("deleted_") and row.email.endswith("@deleted.invalid")
        assert row.current_session_id is None
    # The old username/email are free again.
    from account_kit.service import get_user_by_email, get_user_by_username

    async with api["sessions"]() as db:
        assert await get_user_by_username(db, "d2") is None
        assert await get_user_by_email(db, "d2@example.com") is None
    assert (await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})).status_code == 401


async def test_self_delete_email_factor_and_admin_forbidden(api):
    config = api["config"]
    config.self_delete_enabled = True
    config.two_factor_email_enabled = True
    _admin, admin_headers = await _make_admin(api)
    res = await api["client"].post("/api/auth/me/delete", json={"password": "secret1"}, headers=admin_headers)
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "ADMIN_SELF_DELETE_FORBIDDEN"

    _u, body = await approved_user(api, "d3")
    client = api["client"]
    not_on = await client.post("/api/auth/me/delete/email-code", json={}, headers=bearer(body))
    assert not_on.status_code == 400
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=bearer(body))
    totp = pyotp.TOTP(setup.json()["secret"])
    await client.post("/api/auth/2fa/enable", json={"code": totp.now()}, headers=bearer(body))
    sent = await client.post("/api/auth/me/delete/email-code", json={"language": "en"}, headers=bearer(body))
    assert sent.status_code == 200, sent.text
    mail = api["sent"][-1]
    assert mail["purpose"] == "delete_account"
    ok = await client.post("/api/auth/me/delete", json={"password": "secret1", "email_code": mail["code"]}, headers=bearer(body))
    assert ok.status_code == 200, ok.text


async def test_admin_delete_uses_shared_path(api):
    config = api["config"]
    config.user_delete_mode = "soft"
    _admin, headers = await _make_admin(api)
    victim, _body = await approved_user(api, "victim")
    res = await api["client"].delete(f"/api/admin/account/users/{victim['id']}", headers=headers)
    assert res.status_code == 204
    async with api["sessions"]() as db:
        row = await db.get(User, victim["id"])
        assert row is not None and row.is_active is False
    assert "admin_user_deleted" in await audit_events(api, victim["id"])


async def test_audit_log_events_and_admin_listing(api):
    admin, headers = await _make_admin(api)
    user, _body = await approved_user(api, "au1")
    client = api["client"]
    await client.post("/api/auth/login", data={"username": "au1", "password": "wrong"})
    await client.patch(f"/api/admin/account/users/{user['id']}", json={"tier_code": "pro", "role": "user"}, headers=headers)
    events = await audit_events(api)
    assert "login_success" in events and "login_failed" in events and "admin_user_updated" in events

    listed = await client.get("/api/admin/account/audit-logs", params={"page_size": 2}, headers=headers)
    assert listed.status_code == 200, listed.text
    data = listed.json()
    assert data["total"] >= 4 and len(data["items"]) == 2 and data["page"] == 1
    failed = await client.get("/api/admin/account/audit-logs", params={"event": "login_failed"}, headers=headers)
    items = failed.json()["items"]
    assert items and all(item["event"] == "login_failed" for item in items)
    assert items[0]["meta"]["username"] == "au1"
    mine = await client.get("/api/admin/account/audit-logs", params={"user_id": user["id"]}, headers=headers)
    assert all(item["user_id"] == user["id"] for item in mine.json()["items"])
    updated = await client.get(
        "/api/admin/account/audit-logs", params={"event": "admin_user_updated", "user_id": user["id"]}, headers=headers
    )
    assert updated.json()["items"][0]["meta"]["changes"]["tier_code"] == ["free", "pro"]
    forbidden = await client.get("/api/admin/account/audit-logs", headers=bearer(_body))
    assert forbidden.status_code == 403
    bad = await client.get("/api/admin/account/audit-logs", params={"user_id": "x"}, headers=headers)
    assert bad.status_code == 400


async def test_audit_can_be_disabled_with_hook(api):
    config = api["config"]
    config.audit_log_enabled = False
    hooked = []

    async def on_audit(db, event, user_id, meta):
        hooked.append(event)

    config.on_audit = on_audit
    await approved_user(api, "au2")
    assert await audit_events(api) == []
    assert "login_success" in hooked


async def test_builtin_captcha_off_by_default(api):
    res = await api["client"].get("/api/auth/captcha")
    assert res.status_code in (404, 405)


@pytest.mark.parametrize("backend", ["db", "memory"])
async def test_builtin_captcha_gate(api, backend, monkeypatch):
    pytest.importorskip("PIL")
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from account_kit import captcha_image, mount_account

    base = api["config"]
    base.captcha_builtin = True
    base.captcha_fail_threshold = 1
    base.state_backend = backend

    async def get_db():
        async with api["sessions"]() as session:
            yield session

    app = FastAPI()
    mount_account(app, get_db, base)
    await approved_user(api, "cap1", login=False)
    monkeypatch.setattr(captcha_image.secrets, "choice", lambda seq: "K")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        img = await client.get("/api/auth/captcha")
        assert img.status_code == 200, img.text
        data = img.json()
        assert data["captcha_id"] and data["expires_in"] == 300
        import base64

        assert base64.b64decode(data["image_base64"]).startswith(b"\x89PNG")
        bad = await client.post("/api/auth/login", data={"username": "cap1", "password": "x"})
        assert bad.json()["detail"]["captcha_required"] is True
        need = await client.post("/api/auth/login", data={"username": "cap1", "password": "secret1", "force": "true"})
        assert need.status_code == 428
        wrong = await client.post(
            "/api/auth/login",
            data={"username": "cap1", "password": "secret1", "force": "true", "captcha_id": data["captcha_id"], "captcha_code": "zzzz"},
        )
        assert wrong.json()["detail"]["code"] == "CAPTCHA_INVALID"
        fresh = (await client.get("/api/auth/captcha")).json()
        ok = await client.post(
            "/api/auth/login",
            data={"username": "cap1", "password": "secret1", "force": "true", "captcha_id": fresh["captcha_id"], "captcha_code": "kkkk"},
        )
        assert ok.status_code == 200, ok.text
        reused = await client.post(
            "/api/auth/login",
            data={"username": "cap1", "password": "x", "captcha_id": fresh["captcha_id"], "captcha_code": "KKKK"},
        )
        assert reused.status_code == 401  # below threshold again after success; captcha consumed anyway


async def test_host_verifier_still_wins_over_builtin(api):
    config = api["config"]
    config.captcha_builtin = True
    config.captcha_verifier = lambda cid, code: code == "HOST"
    config.captcha_fail_threshold = 1
    await approved_user(api, "cap2", login=False)
    client = api["client"]
    await client.post("/api/auth/login", data={"username": "cap2", "password": "x"})
    ok = await client.post(
        "/api/auth/login", data={"username": "cap2", "password": "secret1", "force": "true", "captcha_id": "a", "captcha_code": "HOST"}
    )
    assert ok.status_code == 200, ok.text


async def test_login_failures_shared_through_db(api):
    """Two app instances on one database share the captcha failure counters."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from account_kit import mount_account

    config = api["config"]
    config.state_backend = "db"
    config.captcha_verifier = lambda cid, code: False
    config.captcha_fail_threshold = 2
    await approved_user(api, "shared", login=False)
    await api["client"].post("/api/auth/login", data={"username": "shared", "password": "x"})

    async def get_db():
        async with api["sessions"]() as session:
            yield session

    other = FastAPI()
    mount_account(other, get_db, config)
    async with AsyncClient(transport=ASGITransport(app=other), base_url="http://t") as client:
        res = await client.post("/api/auth/login", data={"username": "shared", "password": "x"})
        assert res.json()["detail"]["captcha_required"] is True
    async with api["sessions"]() as db:
        count = await db.scalar(select(func.count()).select_from(RateLimitCounter).where(RateLimitCounter.key.like("login_fail:%")))
        assert count >= 1


async def test_challenges_persist_in_db(api):
    from tests.test_email_2fa_captcha import _challenge, _mfa_user

    api["config"].state_backend = "db"
    await _mfa_user(api)
    await _challenge(api)
    async with api["sessions"]() as db:
        assert await db.scalar(text("SELECT count(*) FROM auth.two_factor_challenges")) == 1
