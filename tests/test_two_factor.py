import time

import pyotp

from account_kit.models import User
from tests.test_auth import _register


async def test_totp_login_challenge(api):
    user = await _register(api, email="mfa@example.com", username="mfa")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    client = api["client"]
    logged = await client.post("/api/auth/login", data={"username": "mfa", "password": "secret1"})
    headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}

    rejected = await client.post("/api/auth/2fa/setup", json={"password": "wrong-password"}, headers=headers)
    assert rejected.status_code == 400, rejected.text
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    totp = pyotp.TOTP(secret)
    earlier = totp.at(time.time() - 30)
    enabled = await client.post("/api/auth/2fa/enable", json={"code": earlier}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    recovery_codes = enabled.json()["recovery_codes"]
    assert len(recovery_codes) == 10

    status = await client.get("/api/auth/2fa/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["enabled"] is True
    assert status.json()["recovery_codes_remaining"] == 10
    assert status.json()["email_available"] is False

    regenerated = await client.post(
        "/api/auth/2fa/recovery-codes/regenerate",
        json={"password": "secret1", "recovery_code": recovery_codes[0], "code": None},
        headers=headers,
    )
    assert regenerated.status_code == 200, regenerated.text
    assert len(regenerated.json()["recovery_codes"]) == 10

    challenged = await client.post("/api/auth/login", data={"username": "mfa", "password": "secret1"})
    assert challenged.status_code == 401
    detail = challenged.json()["detail"]
    assert detail["code"] == "MFA_REQUIRED"

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
    assert done.json()["two_factor_method"] == "totp"
    assert done.json()["trusted_device_token"]
    session = {"Authorization": f"Bearer {done.json()['access_token']}"}
    devices = await client.get("/api/auth/trusted-devices", headers=session)
    assert devices.status_code == 200, devices.text
    listed = devices.json()["devices"]
    assert len(listed) == 1
    assert listed[0]["device_name"] == "lab"
    removed = await client.delete(f"/api/auth/trusted-devices/{listed[0]['id']}", headers=session)
    assert removed.status_code == 200, removed.text
    empty = await client.get("/api/auth/trusted-devices", headers=session)
    assert empty.json()["devices"] == []
    me = await client.get("/api/auth/me", headers=session)
    assert me.status_code == 200
