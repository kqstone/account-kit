"""WeChat Mini Program QR login (0.4.0). Injected WeChat APIs, no network."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from account_kit import init_db, mount_account
from account_kit.captcha import login_fail_tracker
from account_kit.captcha_image import memory_store as captcha_memory
from account_kit.config import AccountKitConfig
from account_kit.models import User, WechatIdentity, WechatLoginTicket
from account_kit.schema_setup import upgrade_sql
from account_kit.state import memory_counters
from account_kit.two_factor.challenges import challenge_store
from tests.conftest import _database_url
from tests.helpers import approved_user, audit_events, bearer, make_admin
from tests.test_auth import _register

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-wxacode"


async def _code2session(js_code: str):
    if js_code in ("bad", "invalid"):
        from account_kit.i18n import account_error

        raise account_error(401, "WECHAT_CODE_INVALID")
    openid = js_code
    unionid = None
    if js_code.startswith("oid:"):
        openid = js_code[4:]
    if "|" in openid:
        openid, unionid = openid.split("|", 1)
    return {"openid": openid, "unionid": unionid or None, "session_key": "must-not-persist"}


async def _getwxacode(scene, page, env_version, check_path, width):
    return PNG + str(scene).encode("ascii")


@pytest.fixture
async def wx():
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

    actions = []

    async def before_action(request, action, info):
        actions.append(action)

    config = AccountKitConfig(
        jwt_secret="test-secret",
        mailer=mailer,
        brand_name="Test",
        session_mode="single_device",
        require_approval=True,
        state_backend=os.environ.get("ACCOUNT_KIT_TEST_STATE_BACKEND", "db"),
        wechat_enabled=True,
        wechat_app_id="wxTESTAPPID",
        wechat_app_secret="",
        wechat_code2session=_code2session,
        wechat_get_wxacode=_getwxacode,
        wechat_check_path=False,
        wechat_env_version="trial",
        wechat_qr_ttl_seconds=120,
        before_action=before_action,
    )
    app = FastAPI()
    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "sent": sent,
            "sessions": sessions,
            "config": config,
            "app": app,
            "actions": actions,
        }
    await engine.dispose()


async def _bind_openid(api, user_id, openid="oid-alice"):
    from datetime import datetime, timezone

    async with api["sessions"]() as db:
        db.add(
            WechatIdentity(
                user_id=user_id,
                app_id="wxTESTAPPID",
                openid=openid,
                bound_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _enable_totp(client, headers, password="secret1"):
    setup = await client.post("/api/auth/2fa/setup", json={"password": password}, headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    totp = pyotp.TOTP(secret)
    # Use the previous window so totp.now() remains valid for a later login (replay window).
    enabled = await client.post("/api/auth/2fa/enable", json={"code": totp.at(time.time() - 30)}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    return totp, enabled.json()["recovery_codes"]


async def _start(client, **extra):
    res = await client.post("/api/auth/login/wechat/start", json=extra or {})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ticket"]
    assert body["scene"]
    assert body["image_base64"]
    assert body["mime"] == "image/png"
    assert "session_key" not in body
    assert "access_token" not in body
    return body


def _no_token(body: dict):
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "session_key" not in body


async def test_disabled_has_no_routes(api):
    res = await api["client"].post("/api/auth/login/wechat/start", json={})
    assert res.status_code == 404
    res = await api["client"].get("/api/auth/wechat/status")
    assert res.status_code in (401, 404)


async def test_not_configured_returns_503():
    engine = create_async_engine(_database_url())
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
    await init_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def get_db():
        async with sessions() as session:
            yield session

    config = AccountKitConfig(jwt_secret="t", wechat_enabled=True, state_backend="memory")
    app = FastAPI()
    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/auth/login/wechat/start", json={})
        assert res.status_code == 503
        assert res.json()["code"] == "WECHAT_NOT_CONFIGURED"
        assert "微信" in res.json()["detail"] or "WeChat" in str(res.json())
    await engine.dispose()


async def test_bound_scan_confirm_status_once(wx):
    user, _tokens = await approved_user(wx, username="alice", login=False)
    await _bind_openid(wx, user["id"], "oid-alice")
    client = wx["client"]
    started = await _start(client, device_name="web")
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-alice"},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["status"] == "scanned"
    assert scanned.json()["username"] == "alice"
    assert "email" not in scanned.json()
    _no_token(scanned.json())

    pending = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert pending.json()["status"] == "scanned"
    assert pending.json()["username"] == "alice"
    _no_token(pending.json())

    confirmed = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started["scene"], "js_code": "oid-alice"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"status": "ok", "purpose": "login"}
    _no_token(confirmed.json())

    first = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "confirmed"
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    token = body["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    second = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert second.json()["status"] == "consumed"
    _no_token(second.json())

    events = await audit_events(wx, user["id"])
    assert "login_wechat" in events
    assert "wechat_start" in wx["actions"]
    assert "wechat_confirm" in wx["actions"]

    async with wx["sessions"]() as db:
        rows = (await db.execute(select(WechatLoginTicket))).scalars().all()
        assert rows
        for row in rows:
            assert row.payload_cipher is None or "session_key" not in (row.payload_cipher or "")
            mapper = inspect(WechatLoginTicket)
            assert "session_key" not in mapper.columns


async def test_expired_ticket_then_refresh(wx):
    user, _ = await approved_user(wx, username="bob")
    await _bind_openid(wx, user["id"], "oid-bob")
    client = wx["client"]
    started = await _start(client)
    async with wx["sessions"]() as db:
        row = (await db.execute(select(WechatLoginTicket))).scalars().first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    expired = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-bob"},
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "WECHAT_TICKET_EXPIRED"
    status = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert status.json()["status"] == "expired"
    _no_token(status.json())
    again = await _start(client)
    assert again["ticket"] != started["ticket"]
    assert again["scene"] != started["scene"]
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": again["scene"], "js_code": "oid-bob"},
    )
    assert scanned.status_code == 200
    assert scanned.json()["status"] == "scanned"


async def test_unbound_bind_existing_without_2fa(wx):
    await approved_user(wx, username="carol", login=False)
    client = wx["client"]
    started = await _start(client)
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-carol"},
    )
    assert scanned.json()["status"] == "unbound"
    _no_token(scanned.json())
    status = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert status.json()["status"] == "unbound"
    assert status.json()["bind_ticket"] == started["ticket"]
    _no_token(status.json())

    wrong = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "carol", "password": "nope"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"

    bound = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "carol", "password": "secret1", "device_name": "web"},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["access_token"]
    me = await client.get("/api/auth/me", headers=bearer(bound.json()))
    assert me.json()["username"] == "carol"
    events = await audit_events(wx)
    assert "wechat_bound" in events
    assert "login_wechat" in events
    assert "wechat_bind" in wx["actions"]


async def test_bind_existing_2fa_via_login_2fa_and_inline(wx):
    user, tokens = await approved_user(wx, username="dave")
    client = wx["client"]
    totp, recovery = await _enable_totp(client, bearer(tokens))
    await client.post("/api/auth/logout", headers=bearer(tokens), json={"all_devices": True})

    started = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-dave"})
    challenged = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "dave", "password": "secret1"},
    )
    assert challenged.status_code == 401, challenged.text
    detail = challenged.json()["detail"]
    assert detail["code"] == "MFA_REQUIRED"
    assert detail["challenge_token"]
    assert detail["bind_ticket"] == started["ticket"]
    assert "methods" in detail

    done = await client.post(
        "/api/auth/login/2fa",
        data={"challenge_token": detail["challenge_token"], "code": totp.now(), "force": "true"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["access_token"]
    me = await client.get("/api/auth/me", headers=bearer(done.json()))
    assert me.json()["username"] == "dave"
    status = await client.get("/api/auth/wechat/status", headers=bearer(done.json()))
    assert status.json()["bound"] is True

    # Unbind and bind again in one step with recovery code.
    unbind = await client.post(
        "/api/auth/wechat/unbind",
        json={"password": "secret1", "recovery_code": recovery[0]},
        headers=bearer(done.json()),
    )
    assert unbind.status_code == 200, unbind.text
    await client.post("/api/auth/logout", headers=bearer(done.json()), json={"all_devices": True})

    started2 = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started2["scene"], "js_code": "oid-dave2"})
    inline = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={
            "bind_ticket": started2["ticket"],
            "username": "dave",
            "password": "secret1",
            "recovery_code": recovery[1],
            "force": True,
        },
    )
    assert inline.status_code == 200, inline.text
    assert inline.json()["access_token"]


async def test_register_require_approval_no_token(wx):
    client = wx["client"]
    started = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-new"})
    await client.post("/api/auth/send-code", json={"email": "new@example.com", "purpose": "register"})
    code = wx["sent"][-1]["code"]
    created = await client.post(
        "/api/auth/login/wechat/register",
        json={
            "bind_ticket": started["ticket"],
            "username": "newbie",
            "email": "new@example.com",
            "password": "secret1",
            "code": code,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["username"] == "newbie"
    assert body["approval_status"] == "pending"
    assert "access_token" not in body
    events = await audit_events(wx)
    assert "wechat_register" in events
    assert "wechat_register" in wx["actions"]

    wx["config"].wechat_allow_register = False
    started2 = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started2["scene"], "js_code": "oid-new2"})
    denied = await client.post(
        "/api/auth/login/wechat/register",
        json={
            "bind_ticket": started2["ticket"],
            "username": "x",
            "email": "x@example.com",
            "password": "secret1",
            "code": "000000",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "WECHAT_REGISTER_DISABLED"


async def test_register_issues_tokens_when_approval_off(wx):
    wx["config"].require_approval = False
    client = wx["client"]
    started = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-ok"})
    await client.post("/api/auth/send-code", json={"email": "ok@example.com", "purpose": "register"})
    code = wx["sent"][-1]["code"]
    created = await client.post(
        "/api/auth/login/wechat/register",
        json={
            "bind_ticket": started["ticket"],
            "username": "okuser",
            "email": "ok@example.com",
            "password": "secret1",
            "code": code,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["access_token"]


async def test_confirm_409_then_force(wx):
    user, tokens = await approved_user(wx, username="erin", login=True)
    await _bind_openid(wx, user["id"], "oid-erin")
    client = wx["client"]
    started = await _start(client, device_name="phone")
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-erin"})
    conflict = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started["scene"], "js_code": "oid-erin"},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "ALREADY_LOGGED_IN"
    status = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert status.json()["status"] == "scanned"
    _no_token(status.json())

    forced = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started["scene"], "js_code": "oid-erin", "force": True},
    )
    assert forced.status_code == 200, forced.text
    first = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    new_token = first.json()["access_token"]
    old = await client.get("/api/auth/me", headers=bearer(tokens))
    assert old.status_code == 401
    assert old.json()["code"] == "SESSION_REPLACED"
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 200


async def test_cancel_and_replay_scan(wx):
    user, _ = await approved_user(wx, username="fran")
    await _bind_openid(wx, user["id"], "oid-fran")
    client = wx["client"]
    started = await _start(client)
    cancel = await client.post("/api/auth/login/wechat/cancel", json={"ticket": started["ticket"]})
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    again = await client.post("/api/auth/login/wechat/cancel", json={"ticket": started["ticket"]})
    assert again.status_code == 200
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-fran"},
    )
    assert scanned.status_code == 400
    status = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert status.json()["status"] == "cancelled"
    _no_token(status.json())


async def test_settings_bind_unbind(wx):
    user, tokens = await approved_user(wx, username="gina")
    client = wx["client"]
    headers = bearer(tokens)
    empty = await client.get("/api/auth/wechat/status", headers=headers)
    assert empty.json() == {"bound": False, "openid_masked": None, "bound_at": None}

    started = await client.post("/api/auth/wechat/bind/start", headers=headers)
    assert started.status_code == 200, started.text
    _no_token(started.json())
    confirmed = await client.post(
        "/api/auth/wechat/bind/confirm",
        json={"ticket": started.json()["scene"], "js_code": "oid-gina"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"status": "ok", "purpose": "bind"}
    _no_token(confirmed.json())
    polled = await client.get("/api/auth/login/wechat/status", params={"ticket": started.json()["ticket"]})
    assert polled.json()["status"] in ("confirmed", "consumed")
    assert "access_token" not in polled.json()
    bound = await client.get("/api/auth/wechat/status", headers=headers)
    assert bound.json()["bound"] is True
    assert "****" in bound.json()["openid_masked"]

    unbind = await client.post("/api/auth/wechat/unbind", json={"password": "secret1"}, headers=headers)
    assert unbind.status_code == 200, unbind.text
    assert unbind.json()["bound"] is False
    gone = await client.get("/api/auth/wechat/status", headers=headers)
    assert gone.json()["bound"] is False
    events = await audit_events(wx, user["id"])
    assert "wechat_bound" in events
    assert "wechat_unbound" in events


async def test_password_change_cancels_tickets_keeps_identity(wx):
    user, tokens = await approved_user(wx, username="hank")
    await _bind_openid(wx, user["id"], "oid-hank")
    client = wx["client"]
    started = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-hank"})
    changed = await client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=bearer(tokens),
    )
    assert changed.status_code == 200, changed.text
    status = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert status.json()["status"] == "cancelled"
    async with wx["sessions"]() as db:
        ident = (await db.execute(select(WechatIdentity).where(WechatIdentity.openid == "oid-hank"))).scalars().first()
        assert ident is not None


async def test_delete_user_cascades_identity(wx):
    wx["config"].self_delete_enabled = True
    user, tokens = await approved_user(wx, username="ivy")
    await _bind_openid(wx, user["id"], "oid-ivy")
    client = wx["client"]
    deleted = await client.post("/api/auth/me/delete", json={"password": "secret1"}, headers=bearer(tokens))
    assert deleted.status_code == 200, deleted.text
    async with wx["sessions"]() as db:
        ident = (await db.execute(select(WechatIdentity))).scalars().first()
        assert ident is None


async def test_rate_limit(wx):
    wx["config"].wechat_login_rate_limit_ip = 2
    client = wx["client"]
    assert (await client.post("/api/auth/login/wechat/start", json={})).status_code == 200
    assert (await client.post("/api/auth/login/wechat/start", json={})).status_code == 200
    third = await client.post("/api/auth/login/wechat/start", json={})
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMITED"


async def test_invalid_js_code_and_already_bound(wx):
    user, _ = await approved_user(wx, username="jade")
    other, tokens = await approved_user(wx, username="kate")
    client = wx["client"]
    started = await _start(client)
    bad = await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "bad"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "WECHAT_CODE_INVALID"

    # Ticket is unbound; identity appears before bind-existing (openid taken by jade).
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-taken"})
    await _bind_openid(wx, user["id"], "oid-taken")
    clash = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "kate", "password": "secret1", "force": True},
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "WECHAT_ALREADY_BOUND"

    headers = bearer(tokens)
    start_bind = await client.post("/api/auth/wechat/bind/start", headers=headers)
    assert start_bind.status_code == 200
    exists = await client.post(
        "/api/auth/wechat/bind/confirm",
        json={"ticket": start_bind.json()["scene"], "js_code": "oid-taken"},
    )
    assert exists.status_code == 409
    assert exists.json()["code"] == "WECHAT_ALREADY_BOUND"


async def test_pending_and_disabled_cannot_confirm(wx):
    user = await _register(wx, email="pend@example.com", username="pend")
    await _bind_openid(wx, user["id"], "oid-pend")
    client = wx["client"]
    started = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started["scene"], "js_code": "oid-pend"})
    blocked = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started["scene"], "js_code": "oid-pend"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "ACCOUNT_PENDING"

    other, _ = await approved_user(wx, username="off")
    async with wx["sessions"]() as db:
        row = await db.get(User, other["id"])
        row.is_active = False
        await db.commit()
    await _bind_openid(wx, other["id"], "oid-off")
    started2 = await _start(client)
    await client.post("/api/auth/login/wechat/scan", json={"ticket": started2["scene"], "js_code": "oid-off"})
    disabled = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started2["scene"], "js_code": "oid-off"},
    )
    assert disabled.status_code == 403
    assert disabled.json()["code"] == "USER_DISABLED"


async def test_secret_not_in_responses_or_status(wx):
    user, tokens = await approved_user(wx, username="leo")
    client = wx["client"]
    started = await _start(client)
    for body in (started,):
        blob = str(body)
        assert "wechat_app_secret" not in blob
        assert wx["config"].wechat_app_secret == ""
    status = await client.get("/api/auth/wechat/status", headers=bearer(tokens))
    assert "secret" not in status.text.lower()
    routes = [getattr(route, "path", "") for route in wx["app"].routes]
    assert "/api/auth/login/wechat" not in routes  # no POST /login/wechat itself


async def _unbound_bind_ticket(client, js_code):
    started = await _start(client)
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": js_code},
    )
    assert scanned.json()["status"] == "unbound"
    return started


async def test_bind_existing_captcha_off_no_gate(wx):
    await approved_user(wx, username="capoff", login=False)
    client = wx["client"]
    started = await _unbound_bind_ticket(client, "oid-capoff")
    for _ in range(3):
        res = await client.post(
            "/api/auth/login/wechat/bind-existing",
            json={"bind_ticket": started["ticket"], "username": "capoff", "password": "bad-pass"},
        )
        assert res.status_code == 401
        assert res.json()["code"] == "INVALID_CREDENTIALS"
        assert "captcha_required" not in str(res.json().get("detail", ""))
    ok = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "capoff", "password": "secret1"},
    )
    assert ok.status_code == 200, ok.text


async def test_bind_existing_captcha_matches_login(wx):
    await approved_user(wx, username="capwx", login=False)
    checked = []

    async def verify(captcha_id, captcha_code):
        checked.append((captcha_id, captcha_code))
        return captcha_id == "cid" and captcha_code == "ABCD"

    config = wx["config"]
    config.captcha_verifier = verify
    config.captcha_fail_threshold = 2
    client = wx["client"]
    started = await _unbound_bind_ticket(client, "oid-capwx")

    async def bind(password, **extra):
        return await client.post(
            "/api/auth/login/wechat/bind-existing",
            json={
                "bind_ticket": started["ticket"],
                "username": "capwx",
                "password": password,
                **extra,
            },
        )

    first = await bind("bad-pass")
    assert first.status_code == 401
    assert first.json()["detail"] == {
        "code": "INVALID_CREDENTIALS",
        "message": "用户名或密码错误",
        "captcha_required": False,
    }
    second = await bind("bad-pass")
    assert second.status_code == 401
    assert second.json()["detail"]["captcha_required"] is True
    need = await bind("secret1")
    assert need.status_code == 428
    assert need.json()["code"] == "CAPTCHA_REQUIRED"
    assert need.json()["detail"] == {"code": "CAPTCHA_REQUIRED", "message": "需要图形验证码", "captcha_required": True}
    wrong = await bind("secret1", captcha_id="cid", captcha_code="XXXX")
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "CAPTCHA_INVALID"
    assert wrong.json()["detail"]["code"] == "CAPTCHA_INVALID"
    ok = await bind("secret1", captcha_id="cid", captcha_code="ABCD")
    assert ok.status_code == 200, ok.text
    assert checked[-1] == ("cid", "ABCD")
    assert ok.json()["access_token"]


async def test_bind_existing_captcha_shares_login_fail_counter(wx):
    await approved_user(wx, username="capshare", login=False)
    config = wx["config"]
    config.captcha_verifier = lambda captcha_id, captcha_code: captcha_id == "cid" and captcha_code == "ABCD"
    config.captcha_fail_threshold = 2
    client = wx["client"]
    for _ in range(2):
        res = await client.post("/api/auth/login", data={"username": "capshare", "password": "bad-pass", "force": "true"})
        assert res.status_code == 401
    started = await _unbound_bind_ticket(client, "oid-capshare")
    need = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "capshare", "password": "secret1"},
    )
    assert need.status_code == 428
    assert need.json()["code"] == "CAPTCHA_REQUIRED"
    ok = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={
            "bind_ticket": started["ticket"],
            "username": "capshare",
            "password": "secret1",
            "captcha_id": "cid",
            "captcha_code": "ABCD",
        },
    )
    assert ok.status_code == 200, ok.text


async def test_bind_existing_admin_always_captcha(wx):
    _, headers = await make_admin(wx, username="capadmin")
    await wx["client"].post("/api/auth/logout", headers=headers, json={"all_devices": True})
    config = wx["config"]
    config.captcha_verifier = lambda captcha_id, captcha_code: captcha_code == "OK"
    config.admin_login_captcha_always = True
    client = wx["client"]
    started = await _unbound_bind_ticket(client, "oid-capadmin")
    need = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={"bind_ticket": started["ticket"], "username": "capadmin", "password": "secret1"},
    )
    assert need.status_code == 428
    assert need.json()["code"] == "CAPTCHA_REQUIRED"
    ok = await client.post(
        "/api/auth/login/wechat/bind-existing",
        json={
            "bind_ticket": started["ticket"],
            "username": "capadmin",
            "password": "secret1",
            "captcha_id": "a",
            "captcha_code": "OK",
            "force": True,
        },
    )
    assert ok.status_code == 200, ok.text


async def test_upgrade_sql_0_4_0_idempotent():
    from account_kit import ensure_schema

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)

        async def columns(conn, table):
            rows = await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'auth' AND table_name = :t ORDER BY column_name"
                ),
                {"t": table},
            )
            return [tuple(row) for row in rows]

        async with engine.connect() as conn:
            expected = {
                "wechat_identities": await columns(conn, "wechat_identities"),
                "wechat_login_tickets": await columns(conn, "wechat_login_tickets"),
            }
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE auth.wechat_login_tickets"))
            await conn.execute(text("DROP TABLE auth.wechat_identities"))
        sql = upgrade_sql("0.4.0")
        for _ in range(2):
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(sql)
        async with engine.connect() as conn:
            assert await columns(conn, "wechat_identities") == expected["wechat_identities"]
            assert await columns(conn, "wechat_login_tickets") == expected["wechat_login_tickets"]
        await ensure_schema(engine)
    finally:
        await engine.dispose()


async def test_i18n_en_wechat_errors(wx):
    client = wx["client"]
    res = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": "not-a-ticket", "js_code": "x"},
        headers={"X-Locale": "en"},
    )
    assert res.status_code == 400
    assert res.json()["code"] == "WECHAT_TICKET_INVALID"
    assert "invalid" in res.json()["detail"].lower()


async def test_bind_code_via_login_scan_confirm_by_scene(wx):
    """Mini Program sends only ``scene`` in ``ticket``; purpose comes from the ticket (server wins)."""
    user, tokens = await approved_user(wx, username="ivan")
    client = wx["client"]
    headers = bearer(tokens)
    started = (await client.post("/api/auth/wechat/bind/start", headers=headers)).json()
    # Client claims "login" but server derives "bind" from the ticket.
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-ivan", "purpose": "login"},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["status"] == "scanned"
    assert scanned.json()["purpose"] == "bind"
    _no_token(scanned.json())
    polled = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert polled.json()["status"] == "scanned"
    confirmed = await client.post(
        "/api/auth/login/wechat/confirm",
        json={"ticket": started["scene"], "js_code": "oid-ivan", "purpose": "bind"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"status": "ok", "purpose": "bind"}
    done = await client.get("/api/auth/login/wechat/status", params={"ticket": started["ticket"]})
    assert done.json()["status"] in ("confirmed", "consumed")
    _no_token(done.json())
    assert (await client.get("/api/auth/wechat/status", headers=headers)).json()["bound"] is True


async def test_login_scan_ignores_client_purpose_bind(wx):
    user, _tokens = await approved_user(wx, username="judy")
    await _bind_openid(wx, user["id"], "oid-judy")
    client = wx["client"]
    started = await _start(client)
    scanned = await client.post(
        "/api/auth/login/wechat/scan",
        json={"ticket": started["scene"], "js_code": "oid-judy", "purpose": "bind"},
    )
    assert scanned.json()["purpose"] == "login"
    assert scanned.json()["username"] == "judy"
