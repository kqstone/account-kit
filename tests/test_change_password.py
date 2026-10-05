import time

import pyotp

from account_kit.config import get_config
from account_kit.models import TrustedDevice, User
from tests.test_auth import _register


async def _approved_headers(api, email="pw@example.com", username="pwuser", password="secret1"):
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    logged = await api["client"].post("/api/auth/login", data={"username": username, "password": password})
    assert logged.status_code == 200, logged.text
    return user, {"Authorization": f"Bearer {logged.json()['access_token']}"}


async def test_change_password_without_email_code(api):
    user, headers = await _approved_headers(api)
    client = api["client"]
    changed = await client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"status": "success", "detail": "密码修改成功"}

    stale = await client.get("/api/auth/me", headers=headers)
    assert stale.status_code == 401

    old = await client.post("/api/auth/login", data={"username": "pwuser", "password": "secret1", "force": "true"})
    assert old.status_code == 401
    fresh = await client.post("/api/auth/login", data={"username": "pwuser", "password": "secret2", "force": "true"})
    assert fresh.status_code == 200, fresh.text
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]


async def test_change_password_rejects_wrong_old_password(api):
    _, headers = await _approved_headers(api, email="wrong@example.com", username="wrongpw")
    bad = await api["client"].post(
        "/api/auth/change-password",
        json={"old_password": "nope", "new_password": "secret2"},
        headers=headers,
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "旧密码错误"


async def test_change_password_revokes_trusted_devices(api):
    user = await _register(api, email="mfa-pw@example.com", username="mfapw")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    client = api["client"]
    logged = await client.post("/api/auth/login", data={"username": "mfapw", "password": "secret1"})
    headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=headers)
    totp = pyotp.TOTP(setup.json()["secret"])
    enabled = await client.post("/api/auth/2fa/enable", json={"code": totp.at(time.time() - 30)}, headers=headers)
    assert enabled.status_code == 200, enabled.text

    challenged = await client.post("/api/auth/login", data={"username": "mfapw", "password": "secret1"})
    detail = challenged.json()["detail"]
    done = await client.post(
        "/api/auth/login/2fa",
        data={
            "challenge_token": detail["challenge_token"],
            "code": totp.now(),
            "force": "true",
            "trust_device": "true",
            "device_name": "lab",
        },
    )
    assert done.status_code == 200, done.text
    session = {"Authorization": f"Bearer {done.json()['access_token']}"}
    devices = await client.get("/api/auth/trusted-devices", headers=session)
    assert len(devices.json()["devices"]) == 1

    changed = await client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret9"},
        headers=session,
    )
    assert changed.status_code == 200, changed.text

    async with api["sessions"]() as db:
        from sqlalchemy import select

        rows = (
            await db.execute(
                select(TrustedDevice).where(
                    TrustedDevice.user_id == user["id"],
                    TrustedDevice.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        assert rows == []

    again = await client.post("/api/auth/login", data={"username": "mfapw", "password": "secret9"})
    assert again.status_code == 401
    assert again.json()["detail"]["code"] == "MFA_REQUIRED"


async def test_change_password_email_code_optional_flag(api):
    _, headers = await _approved_headers(api, email="flag@example.com", username="flagpw")
    client = api["client"]
    get_config().change_password_require_email_code = True
    missing = await client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=headers,
    )
    assert missing.status_code == 400

    sent = await client.post(
        "/api/auth/send-code",
        json={"email": "flag@example.com", "purpose": "change_password", "language": "zh"},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    code = api["sent"][-1]["code"]
    ok = await client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2", "code": code},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text


async def test_change_password_calls_hook(api):
    called = []

    async def hook(db, user):
        called.append(str(user.id))

    get_config().on_password_changed = hook
    user, headers = await _approved_headers(api, email="hook@example.com", username="hookpw")
    res = await api["client"].post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert called == [user["id"]]


async def test_patch_me_still_requires_email_code(api):
    _, headers = await _approved_headers(api, email="patch@example.com", username="patchpw")
    client = api["client"]
    missing = await client.patch(
        "/api/auth/me",
        json={"current_password": "secret1", "new_password": "secret2"},
        headers=headers,
    )
    assert missing.status_code == 400
    sent = await client.post(
        "/api/auth/send-code",
        json={"email": "patch@example.com", "purpose": "change_password"},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    code = api["sent"][-1]["code"]
    ok = await client.patch(
        "/api/auth/me",
        json={"current_password": "secret1", "new_password": "secret2", "code": code},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]
