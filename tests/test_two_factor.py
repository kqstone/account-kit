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

    setup = await client.post("/api/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    totp = pyotp.TOTP(secret)
    earlier = totp.at(time.time() - 30)
    enabled = await client.post("/api/auth/2fa/enable", json={"code": earlier}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    assert len(enabled.json()["recovery_codes"]) == 10

    challenged = await client.post("/api/auth/login", data={"username": "mfa", "password": "secret1"})
    assert challenged.status_code == 401
    detail = challenged.json()["detail"]
    assert detail["code"] == "MFA_REQUIRED"

    done = await client.post(
        "/api/auth/login/2fa",
        data={"challenge_token": detail["challenge_token"], "code": totp.now(), "force": "true"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["two_factor_method"] == "totp"
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {done.json()['access_token']}"})
    assert me.status_code == 200
