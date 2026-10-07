"""Admin security: single-admin lock, lockout, 2FA, session, audit."""

import time
from datetime import datetime, timezone

import pyotp
import pytest
from jose import jwt
from sqlalchemy.exc import IntegrityError

from account_kit import ensure_admin
from account_kit.admin_setup import AdminSetupError
from account_kit.config import get_config
from account_kit.models import User
from account_kit.security import hash_password
from account_kit.seed import default_role
from tests.helpers import approved_user, audit_events, bearer, make_admin


def _code(res):
    detail = res.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


async def test_patch_me_cannot_set_is_admin(api):
    _user, body = await approved_user(api, "me1")
    res = await api["client"].patch("/api/auth/me", json={"is_admin": True}, headers=bearer(body))
    assert res.status_code == 200, res.text
    assert res.json()["user"]["is_admin"] is False
    me = await api["client"].get("/api/auth/me", headers=bearer(body))
    assert me.json()["is_admin"] is False


async def test_register_ignores_is_admin(api):
    client = api["client"]
    email = "ign@example.com"
    await client.post("/api/auth/send-code", json={"email": email, "purpose": "register", "language": "zh"})
    code = api["sent"][-1]["code"]
    created = await client.post(
        "/api/auth/register",
        json={
            "username": "ign",
            "email": email,
            "password": "secret1",
            "code": code,
            "is_admin": True,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["is_admin"] is False


async def test_cannot_patch_is_admin(api):
    admin, headers = await make_admin(api, "boss")
    victim, _body = await approved_user(api, "v1")
    client = api["client"]
    for target, payload in (
        (victim["id"], {"is_admin": True}),
        (victim["id"], {"is_admin": False}),
        (admin["id"], {"is_admin": True}),
        (admin["id"], {"is_admin": False}),
    ):
        res = await client.patch(f"/api/admin/account/users/{target}", json=payload, headers=headers)
        assert res.status_code == 400, res.text
        assert _code(res) == "ADMIN_FLAG_IMMUTABLE"
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["is_admin"] is True
    listed = await client.get("/api/admin/account/users", headers=headers)
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id[victim["id"]]["is_admin"] is False
    assert by_id[admin["id"]]["is_admin"] is True
    assert "admin_protected" in await audit_events(api, victim["id"])


async def test_cannot_delete_or_deactivate_admin(api):
    admin, headers = await make_admin(api, "boss")
    victim, _body = await approved_user(api, "v2")
    client = api["client"]
    stopped = await client.patch(
        f"/api/admin/account/users/{admin['id']}", json={"is_active": False}, headers=headers
    )
    assert stopped.status_code == 400
    assert _code(stopped) == "ADMIN_DEACTIVATE_FORBIDDEN"
    revoked = await client.patch(
        f"/api/admin/account/users/{admin['id']}", json={"approval_status": "rejected"}, headers=headers
    )
    assert revoked.status_code == 400
    assert _code(revoked) == "ADMIN_DEACTIVATE_FORBIDDEN"
    deleted = await client.delete(f"/api/admin/account/users/{admin['id']}", headers=headers)
    assert deleted.status_code == 400
    assert _code(deleted) == "ADMIN_DELETE_FORBIDDEN"
    ok_stop = await client.patch(
        f"/api/admin/account/users/{victim['id']}", json={"is_active": False}, headers=headers
    )
    assert ok_stop.status_code == 200, ok_stop.text
    assert ok_stop.json()["is_active"] is False
    gone = await client.delete(f"/api/admin/account/users/{victim['id']}", headers=headers)
    assert gone.status_code == 204
    async with api["sessions"]() as db:
        row = await db.get(User, admin["id"])
        assert row is not None and row.is_admin is True and row.is_active is True


async def test_ensure_admin_idempotent_and_refuses(api):
    cfg = get_config()
    async with api["sessions"]() as db:
        first = await ensure_admin(db, "root", "root@example.com", "secret1", config=cfg)
        again = await ensure_admin(db, "root", "other@example.com", "changed9", config=cfg)
        assert again.id == first.id
        assert again.email == "root@example.com"
        assert again.hashed_password == first.hashed_password
        with pytest.raises(AdminSetupError) as other:
            await ensure_admin(db, "other", "other@example.com", "secret1", config=cfg)
        assert other.value.code == "ADMIN_ALREADY_EXISTS"
        reset = await ensure_admin(db, "root", "root@example.com", "secret99", reset_password=True, config=cfg)
        assert reset.username == "root"


async def test_ensure_admin_refuses_takeover_when_no_admin(api):
    cfg = get_config()
    await approved_user(api, "plain", email="plain@example.com", login=False)
    async with api["sessions"]() as db:
        with pytest.raises(AdminSetupError) as name_err:
            await ensure_admin(db, "plain", "fresh@example.com", "secret1", config=cfg)
        assert name_err.value.code == "ADMIN_USERNAME_TAKEN"
        with pytest.raises(AdminSetupError) as email_err:
            await ensure_admin(db, "fresh", "plain@example.com", "secret1", config=cfg)
        assert email_err.value.code == "ADMIN_EMAIL_TAKEN"


async def test_partial_unique_index_rejects_second_admin(api):
    await make_admin(api, "only")
    async with api["sessions"]() as db:
        role = await default_role(db)
        db.add(
            User(
                username="second",
                email="second@example.com",
                hashed_password=hash_password("secret1"),
                role=role.code,
                is_admin=True,
                is_active=True,
                approval_status="approved",
                approved_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_admin_login_lockout(api):
    cfg = get_config()
    cfg.admin_login_lockout_attempts = 3
    cfg.login_lockout_attempts = 0
    await make_admin(api, "lockadmin")
    await approved_user(api, "norm", login=False)
    client = api["client"]
    first = await client.post("/api/auth/login", data={"username": "lockadmin", "password": "wrong", "force": "true"})
    assert first.status_code == 401
    second = await client.post("/api/auth/login", data={"username": "lockadmin", "password": "wrong", "force": "true"})
    assert second.status_code == 401
    third = await client.post("/api/auth/login", data={"username": "lockadmin", "password": "wrong", "force": "true"})
    assert third.status_code == 429
    assert _code(third) == "ACCOUNT_LOCKED"
    assert third.json()["detail"]["retry_after"] >= 1
    still = await client.post("/api/auth/login", data={"username": "lockadmin", "password": "secret1", "force": "true"})
    assert still.status_code == 429
    for _ in range(6):
        res = await client.post("/api/auth/login", data={"username": "norm", "password": "wrong", "force": "true"})
        assert res.status_code == 401
    ok = await client.post("/api/auth/login", data={"username": "norm", "password": "secret1", "force": "true"})
    assert ok.status_code == 200, ok.text


async def test_admin_login_lockout_clears_on_success(api):
    cfg = get_config()
    cfg.admin_login_lockout_attempts = 3
    await make_admin(api, "clearadmin")
    client = api["client"]
    await client.post("/api/auth/login", data={"username": "clearadmin", "password": "wrong", "force": "true"})
    await client.post("/api/auth/login", data={"username": "clearadmin", "password": "wrong", "force": "true"})
    ok = await client.post("/api/auth/login", data={"username": "clearadmin", "password": "secret1", "force": "true"})
    assert ok.status_code == 200, ok.text
    again = await client.post("/api/auth/login", data={"username": "clearadmin", "password": "wrong", "force": "true"})
    assert again.status_code == 401


async def test_admin_require_2fa(api):
    cfg = get_config()
    cfg.admin_require_2fa = True
    cfg.two_factor_email_enabled = True
    admin, headers = await make_admin(api, "mfaadmin")
    client = api["client"]
    logged = await client.post("/api/auth/login", data={"username": "mfaadmin", "password": "secret1", "force": "true"})
    assert logged.status_code == 200, logged.text
    token_headers = bearer(logged.json())
    blocked = await client.get("/api/admin/account/users", headers=token_headers)
    assert blocked.status_code == 403
    assert _code(blocked) == "ADMIN_2FA_REQUIRED"
    missing_pw = await client.post("/api/auth/2fa/setup", json={}, headers=token_headers)
    assert missing_pw.status_code == 400
    assert _code(missing_pw) == "PASSWORD_REQUIRED"
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=token_headers)
    assert setup.status_code == 200, setup.text
    totp = pyotp.TOTP(setup.json()["secret"])
    enabled = await client.post("/api/auth/2fa/enable", json={"code": totp.now()}, headers=token_headers)
    assert enabled.status_code == 200, enabled.text
    challenged = await client.post(
        "/api/auth/login", data={"username": "mfaadmin", "password": "secret1", "force": "true"}
    )
    assert challenged.status_code == 401
    detail = challenged.json()["detail"]
    assert detail["code"] == "MFA_REQUIRED"
    assert "email" not in detail["methods"]
    sent = await client.post("/api/auth/login/2fa/email/send", json={"challenge_token": detail["challenge_token"]})
    assert sent.status_code == 400
    assert _code(sent) == "ADMIN_EMAIL_2FA_FORBIDDEN"
    done = await client.post(
        "/api/auth/login/2fa",
        data={
            "challenge_token": detail["challenge_token"],
            "code": totp.at(time.time() + 30),
            "force": "true",
            "trust_device": "true",
        },
    )
    assert done.status_code == 200, done.text
    trusted = done.json().get("trusted_device_token")
    ok = await client.get("/api/admin/account/users", headers=bearer(done.json()))
    assert ok.status_code == 200, ok.text
    skipped = await client.post(
        "/api/auth/login",
        data={
            "username": "mfaadmin",
            "password": "secret1",
            "force": "true",
            "trusted_device_token": trusted or "",
        },
    )
    assert skipped.status_code == 401
    assert skipped.json()["detail"]["code"] == "MFA_REQUIRED"


async def test_admin_ip_allowlist(api):
    admin, headers = await make_admin(api, "ipadmin")
    cfg = get_config()
    cfg.client_ip = lambda _request: "10.0.0.8"
    cfg.admin_ip_allowlist = ("10.0.0.1",)
    denied = await api["client"].get("/api/admin/account/users", headers=headers)
    assert denied.status_code == 403
    assert _code(denied) == "ADMIN_IP_FORBIDDEN"
    cfg.admin_ip_allowlist = ("10.0.0.8",)
    allowed = await api["client"].get("/api/admin/account/users", headers=headers)
    assert allowed.status_code == 200, allowed.text
    cfg.admin_ip_allowlist = ()
    open_ok = await api["client"].get("/api/admin/account/users", headers=headers)
    assert open_ok.status_code == 200


async def test_admin_token_ttl_and_no_refresh(api):
    cfg = get_config()
    cfg.refresh_token_enabled = True
    cfg.admin_refresh_disabled = True
    cfg.admin_access_token_expire_minutes = 5
    _admin, admin_body = await make_admin(api, "ttladmin")
    # make_admin logs in before is_admin is set, so login again as admin.
    admin_login = await api["client"].post(
        "/api/auth/login", data={"username": "ttladmin", "password": "secret1", "force": "true"}
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_tokens = admin_login.json()
    assert admin_tokens.get("refresh_token") is None
    claims = jwt.get_unverified_claims(admin_tokens["access_token"])
    left = claims["exp"] - time.time()
    assert 4 * 60 < left <= 5 * 60 + 15
    _u, user_tokens = await approved_user(api, "ttluser")
    assert user_tokens.get("refresh_token")
    user_claims = jwt.get_unverified_claims(user_tokens["access_token"])
    user_left = user_claims["exp"] - time.time()
    assert user_left > 60 * 60


async def test_admin_password_min_length(api):
    cfg = get_config()
    cfg.admin_password_min_length = 12
    _admin, headers = await make_admin(api, "pwadmin")
    short = await api["client"].post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=headers,
    )
    assert short.status_code == 400
    _u, user_body = await approved_user(api, "pwuser")
    ok = await api["client"].post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=bearer(user_body),
    )
    assert ok.status_code == 200, ok.text


async def test_admin_login_audit_meta(api):
    await make_admin(api, "audadmin")
    await approved_user(api, "auduser", login=False)
    client = api["client"]
    await client.post("/api/auth/login", data={"username": "audadmin", "password": "wrong", "force": "true"})
    await client.post("/api/auth/login", data={"username": "auduser", "password": "wrong", "force": "true"})
    await client.post("/api/auth/login", data={"username": "audadmin", "password": "secret1", "force": "true"})
    from sqlalchemy import select

    from account_kit.models import AuthAuditLog
    import json

    async with api["sessions"]() as db:
        rows = (await db.execute(select(AuthAuditLog).order_by(AuthAuditLog.created_at))).scalars().all()
        metas = []
        for row in rows:
            if row.event in ("login_success", "login_failed") and row.meta:
                metas.append((row.event, json.loads(row.meta)))
    failed_admin = [m for e, m in metas if e == "login_failed" and m.get("username") == "audadmin"]
    failed_user = [m for e, m in metas if e == "login_failed" and m.get("username") == "auduser"]
    success_admin = [m for e, m in metas if e == "login_success" and m.get("is_admin") is True]
    assert failed_admin and failed_admin[0]["is_admin"] is True
    assert failed_user and failed_user[0]["is_admin"] is False
    assert success_admin


async def test_query_token_rejected_on_admin(api):
    _admin, body = await make_admin(api, "qadmin")
    token = body["access_token"] if "access_token" in body else None
    # make_admin logs in before promoting; login again so token is valid and user is admin.
    logged = await api["client"].post(
        "/api/auth/login", data={"username": "qadmin", "password": "secret1", "force": "true"}
    )
    token = logged.json()["access_token"]
    res = await api["client"].get("/api/admin/account/users", params={"token": token})
    assert res.status_code == 401
    ok = await api["client"].get("/api/admin/account/users", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200, ok.text


async def test_approval_revoked_blocks_access(api):
    _admin, headers = await make_admin(api, "appradmin")
    user, body = await approved_user(api, "appruser")
    revoked = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}", json={"approval_status": "rejected"}, headers=headers
    )
    assert revoked.status_code == 200, revoked.text
    me = await api["client"].get("/api/auth/me", headers=bearer(body))
    assert me.status_code == 403
    assert me.json()["detail"] == "账号尚未通过审批"
