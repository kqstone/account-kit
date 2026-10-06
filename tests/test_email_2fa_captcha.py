import pyotp

from account_kit.config import get_config
from account_kit.models import User
from tests.test_auth import _register


async def _mfa_user(api, username="mfa", email="mfa@example.com"):
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    client = api["client"]
    logged = await client.post("/api/auth/login", data={"username": username, "password": "secret1"})
    assert logged.status_code == 200, logged.text
    headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    setup = await client.post("/api/auth/2fa/setup", json={"password": "secret1"}, headers=headers)
    totp = pyotp.TOTP(setup.json()["secret"])
    enabled = await client.post("/api/auth/2fa/enable", json={"code": totp.now()}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    return headers, totp, enabled.json()["recovery_codes"]


async def _challenge(api, username="mfa"):
    res = await api["client"].post(
        "/api/auth/login", data={"username": username, "password": "secret1", "device_name": "phone"}
    )
    assert res.status_code == 401, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "MFA_REQUIRED"
    return detail


async def test_email_fallback_off_by_default(api):
    await _mfa_user(api)
    client = api["client"]
    detail = await _challenge(api)
    assert detail["email_available"] is False
    assert detail["methods"] == ["totp", "recovery"]
    assert detail["trusted_device_days"] == 30
    assert detail["expires_in"] == 300
    sent = await client.post("/api/auth/login/2fa/email/send", json={"challenge_token": detail["challenge_token"]})
    assert sent.status_code == 404
    res = await client.post(
        "/api/auth/login/2fa", data={"challenge_token": detail["challenge_token"], "email_code": "123456"}
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "EMAIL_UNAVAILABLE"


async def test_email_fallback_login(api):
    await _mfa_user(api)
    config = get_config()
    config.two_factor_email_enabled = True
    config.trusted_device_days = 14
    client = api["client"]
    detail = await _challenge(api)
    assert detail["email_available"] is True
    assert detail["methods"] == ["totp", "recovery", "email"]
    assert detail["trusted_device_days"] == 14
    token = detail["challenge_token"]

    sent = await client.post("/api/auth/login/2fa/email/send", json={"challenge_token": token, "language": "zh"})
    assert sent.status_code == 200, sent.text
    assert sent.json() == {"status": "success", "email": "mf***@example.com", "expires_in": 300, "cooldown": 60}
    mail = api["sent"][-1]
    assert mail["purpose"] == "login_2fa"
    assert mail["to"] == "mfa@example.com"
    again = await client.post("/api/auth/login/2fa/email/send", json={"challenge_token": token})
    assert again.status_code == 429
    assert again.json()["detail"]["code"] == "EMAIL_CODE_TOO_FREQUENT"

    missing = await client.post("/api/auth/login/2fa", data={"challenge_token": token})
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "MFA_CODE_REQUIRED"
    wrong = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "email_code": "000000"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"]["code"] == "EMAIL_CODE_INVALID"
    assert wrong.json()["detail"]["attempts_left"] == 4

    # The account is still signed in elsewhere (single_device): 409, then force without a code.
    busy = await client.post(
        "/api/auth/login/2fa",
        data={"challenge_token": token, "email_code": mail["code"], "device_name": "phone", "trust_device": "true"},
    )
    assert busy.status_code == 409, busy.text
    assert busy.json()["detail"]["code"] == "ALREADY_LOGGED_IN"
    done = await client.post(
        "/api/auth/login/2fa",
        data={"challenge_token": token, "force": "true", "device_name": "phone", "trust_device": "true"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["two_factor_method"] == "email"
    assert done.json()["trusted_device_token"]
    reused = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "force": "true"})
    assert reused.status_code == 401
    assert reused.json()["detail"]["code"] == "MFA_CHALLENGE_INVALID"
    sent_again = await client.post("/api/auth/login/2fa/email/send", json={"challenge_token": token})
    assert sent_again.status_code == 401

    trusted = await client.post(
        "/api/auth/login",
        data={
            "username": "mfa",
            "password": "secret1",
            "force": "true",
            "trusted_device_token": done.json()["trusted_device_token"],
        },
    )
    assert trusted.status_code == 200, trusted.text


async def test_email_code_used_once_and_attempt_limit(api):
    _headers, totp, recovery = await _mfa_user(api)
    get_config().two_factor_email_enabled = True
    client = api["client"]
    token = (await _challenge(api))["challenge_token"]
    for left in (4, 3, 2, 1):
        res = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": "000000"})
        assert res.status_code == 400
        assert res.json()["detail"] == {"code": "MFA_CODE_INVALID", "message": "验证码错误", "attempts_left": left}
    res = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": "000000"})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "MFA_TOO_MANY_ATTEMPTS"
    gone = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": totp.now()})
    assert gone.json()["detail"]["code"] == "MFA_CHALLENGE_INVALID"

    token = (await _challenge(api))["challenge_token"]
    res = await client.post(
        "/api/auth/login/2fa", data={"challenge_token": token, "recovery_code": recovery[0], "force": "true"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["two_factor_method"] == "recovery"
    assert res.json()["recovery_codes_remaining"] == 9


async def test_disable_with_email_code(api):
    headers, _totp, _recovery = await _mfa_user(api)
    client = api["client"]
    off = await client.post("/api/auth/2fa/disable/email-code", json={"language": "en"}, headers=headers)
    assert off.status_code == 404
    get_config().two_factor_email_enabled = True
    status = await client.get("/api/auth/2fa/status", headers=headers)
    assert status.json()["email_available"] is True
    sent = await client.post("/api/auth/2fa/disable/email-code", json={"language": "en"}, headers=headers)
    assert sent.status_code == 200, sent.text
    mail = api["sent"][-1]
    assert mail["purpose"] == "disable_2fa"
    assert mail["language"] == "en"
    bad = await client.post("/api/auth/2fa/disable", json={"password": "secret1", "email_code": "000000"}, headers=headers)
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "EMAIL_CODE_INVALID"
    ok = await client.post(
        "/api/auth/2fa/disable", json={"password": "secret1", "email_code": mail["code"]}, headers=headers
    )
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"enabled": False}


async def _approved(api, username="cap", email="cap@example.com"):
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()


async def test_captcha_off_by_default(api):
    await _approved(api)
    for _ in range(6):
        res = await api["client"].post("/api/auth/login", data={"username": "cap", "password": "bad-pass"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Incorrect username or password"


async def test_login_captcha_after_failures(api):
    await _approved(api)
    checked = []

    async def verify(captcha_id, captcha_code):
        checked.append((captcha_id, captcha_code))
        return captcha_id == "cid" and captcha_code == "ABCD"

    config = get_config()
    config.captcha_verifier = verify
    config.captcha_fail_threshold = 2
    client = api["client"]

    async def login(password, **extra):
        return await client.post(
            "/api/auth/login", data={"username": "cap", "password": password, "force": "true", **extra}
        )

    first = await login("bad-pass")
    assert first.status_code == 401
    assert first.json()["detail"] == {
        "code": "INVALID_CREDENTIALS",
        "message": "Incorrect username or password",
        "captcha_required": False,
    }
    second = await login("bad-pass")
    assert second.json()["detail"]["captcha_required"] is True
    need = await login("secret1")
    assert need.status_code == 428
    assert need.json()["detail"] == {"code": "CAPTCHA_REQUIRED", "message": "需要图形验证码", "captcha_required": True}
    wrong = await login("secret1", captcha_id="cid", captcha_code="XXXX")
    assert wrong.status_code == 400
    assert wrong.json()["detail"]["code"] == "CAPTCHA_INVALID"
    # Username-keyed counter applies to other IPs too.
    ok = await login("secret1", captcha_id="cid", captcha_code="ABCD")
    assert ok.status_code == 200, ok.text
    assert checked[-1] == ("cid", "ABCD")
    after = await login("bad-pass")
    assert after.status_code == 401
    assert after.json()["detail"]["captcha_required"] is False


async def test_captcha_counts_unknown_users_by_ip(api):
    config = get_config()
    config.captcha_verifier = lambda captcha_id, captcha_code: captcha_code == "OK"
    config.captcha_fail_threshold = 2
    config.client_ip = lambda request: request.headers.get("x-real-ip", "")
    client = api["client"]
    for name in ("ghost1", "ghost2"):
        res = await client.post(
            "/api/auth/login", data={"username": name, "password": "x"}, headers={"X-Real-IP": "10.0.0.9"}
        )
        assert res.status_code == 401
    blocked = await client.post(
        "/api/auth/login", data={"username": "ghost3", "password": "x"}, headers={"X-Real-IP": "10.0.0.9"}
    )
    assert blocked.status_code == 428
    other_ip = await client.post(
        "/api/auth/login", data={"username": "ghost3", "password": "x"}, headers={"X-Real-IP": "10.0.0.10"}
    )
    assert other_ip.status_code == 401
    passed = await client.post(
        "/api/auth/login",
        data={"username": "ghost3", "password": "x", "captcha_id": "a", "captcha_code": "OK"},
        headers={"X-Real-IP": "10.0.0.9"},
    )
    assert passed.status_code == 401
    assert passed.json()["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_challenge_ttl_and_attempts_from_config(api):
    import time as _time

    from sqlalchemy import update

    from account_kit.models import TwoFactorChallenge
    from account_kit.two_factor.challenges import _h, load_challenge

    _headers, totp, _recovery = await _mfa_user(api)
    config = get_config()
    config.two_factor_challenge_ttl_seconds = 90
    config.two_factor_max_attempts = 2
    client = api["client"]
    detail = await _challenge(api)
    assert detail["expires_in"] == 90
    async with api["sessions"]() as db:
        item = await load_challenge(db, config, detail["challenge_token"])
    assert 85 <= item.expires_at - _time.monotonic() <= 90
    token = detail["challenge_token"]
    first = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": "000000"})
    assert first.json()["detail"]["attempts_left"] == 1
    # Changed at runtime: read on each request.
    config.two_factor_max_attempts = 3
    second = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": "000000"})
    assert second.json()["detail"]["attempts_left"] == 1
    third = await client.post("/api/auth/login/2fa", data={"challenge_token": token, "code": "000000"})
    assert third.status_code == 401
    assert third.json()["detail"]["code"] == "MFA_TOO_MANY_ATTEMPTS"

    item_token = (await _challenge(api))["challenge_token"]
    from datetime import datetime, timedelta, timezone

    if not config.use_db_state():
        from account_kit.two_factor.challenges import challenge_store

        challenge_store.get(item_token).expires_at = _time.monotonic() - 1
    else:
        async with api["sessions"]() as db:
            await db.execute(
                update(TwoFactorChallenge)
                .where(TwoFactorChallenge.token_hash == _h(item_token))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            await db.commit()
    expired = await client.post("/api/auth/login/2fa", data={"challenge_token": item_token, "code": totp.now()})
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "MFA_CHALLENGE_INVALID"
