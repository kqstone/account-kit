"""0.2.2 item 1: wrong-attempt cap, send limits, hooks."""

import pytest
from fastapi import HTTPException

from tests.helpers import approved_user, audit_events, bearer


async def _send(api, email, purpose="register", headers=None, ip=None):
    hdrs = dict(headers or {})
    if ip:
        hdrs["X-Real-IP"] = ip
    return await api["client"].post(
        "/api/auth/send-code", json={"email": email, "purpose": purpose, "language": "zh"}, headers=hdrs
    )


async def test_wrong_code_attempts_invalidate_code(api):
    client = api["client"]
    assert (await _send(api, "cap@example.com")).status_code == 200
    code = api["sent"][-1]["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        res = await client.post("/api/auth/verify-code", json={"email": "cap@example.com", "purpose": "register", "code": wrong})
        assert res.status_code == 400
        assert res.json()["detail"] == "验证码错误或已失效"
    locked = await client.post("/api/auth/verify-code", json={"email": "cap@example.com", "purpose": "register", "code": wrong})
    assert locked.status_code == 400
    assert locked.json()["detail"] == "验证码错误次数过多，请重新获取验证码"
    # The right code no longer works: it was invalidated.
    res = await client.post(
        "/api/auth/register",
        json={"username": "cap", "email": "cap@example.com", "password": "secret1", "code": code},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "验证码错误或已失效"
    assert "verification_code_locked" in await audit_events(api)


async def test_correct_code_resets_wrong_counter(api):
    client = api["client"]
    api["config"].verify_code_max_attempts = 3
    await _send(api, "ok@example.com")
    code = api["sent"][-1]["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(2):
        await client.post("/api/auth/verify-code", json={"email": "ok@example.com", "purpose": "register", "code": wrong})
    good = await client.post("/api/auth/verify-code", json={"email": "ok@example.com", "purpose": "register", "code": code})
    assert good.status_code == 200
    for _ in range(2):
        await client.post("/api/auth/verify-code", json={"email": "ok@example.com", "purpose": "register", "code": wrong})
    # Two more wrong after a success: still below the cap of 3.
    created = await client.post(
        "/api/auth/register", json={"username": "okuser", "email": "ok@example.com", "password": "secret1", "code": code}
    )
    assert created.status_code == 200, created.text


async def test_reset_password_wrong_attempts(api):
    await approved_user(api, "rp", login=False)
    client = api["client"]
    await _send(api, "rp@example.com", "reset_password")
    code = api["sent"][-1]["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        await client.post("/api/auth/reset-password", json={"email": "rp@example.com", "code": wrong, "new_password": "secret9"})
    res = await client.post("/api/auth/reset-password", json={"email": "rp@example.com", "code": code, "new_password": "secret9"})
    assert res.status_code == 400


async def test_send_code_rate_limit_per_email(api):
    config = api["config"]
    config.send_code_rate_limit_email = 2
    # The 5-minute per-purpose resend window would hide the limit; use distinct purposes.
    first = await _send(api, "rl@example.com", "register")
    assert first.status_code == 200
    second = await _send(api, "rl@example.com", "reset_password")
    assert second.status_code == 200
    third = await _send(api, "rl@example.com", "reset_password")
    assert third.status_code == 429
    detail = third.json()["detail"]
    assert detail["code"] == "RATE_LIMITED"
    assert detail["retry_after"] > 0
    assert third.headers.get("retry-after")


async def test_send_code_rate_limit_per_ip(api):
    config = api["config"]
    config.send_code_rate_limit_ip = 2
    config.client_ip = lambda request: request.headers.get("x-real-ip", "")
    assert (await _send(api, "a1@example.com", ip="10.1.1.1")).status_code == 200
    assert (await _send(api, "a2@example.com", ip="10.1.1.1")).status_code == 200
    blocked = await _send(api, "a3@example.com", ip="10.1.1.1")
    assert blocked.status_code == 429
    other = await _send(api, "a3@example.com", ip="10.1.1.2")
    assert other.status_code == 200


async def test_limits_can_be_disabled(api):
    config = api["config"]
    config.send_code_rate_limit_email = 0
    config.send_code_rate_limit_ip = 0
    for purpose in ("register", "reset_password"):
        assert (await _send(api, "free@example.com", purpose)).status_code == 200


async def test_before_send_code_and_before_action_hooks(api):
    config = api["config"]
    seen = []

    async def before_send(request, email, purpose):
        seen.append(("send", email, purpose))
        if email.startswith("blocked"):
            raise HTTPException(status_code=403, detail="blocked by host")

    async def before_action(request, action, info):
        seen.append((action, info.get("purpose")))

    config.before_send_code = before_send
    config.before_action = before_action
    ok = await _send(api, "hook@example.com")
    assert ok.status_code == 200
    blocked = await _send(api, "blocked@example.com")
    assert blocked.status_code == 403
    assert ("send", "hook@example.com", "register") in seen
    assert ("send_code", "register") in seen
    await api["client"].post("/api/auth/verify-code", json={"email": "hook@example.com", "purpose": "register", "code": "123456"})
    assert ("verify_code", "register") in seen


async def test_change_password_email_code_required_detail(api):
    _user, body = await approved_user(api, "cpw")
    api["config"].change_password_require_email_code = True
    res = await api["client"].post(
        "/api/auth/change-password", json={"old_password": "secret1", "new_password": "secret2"}, headers=bearer(body)
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "EMAIL_CODE_REQUIRED"


async def test_two_factor_email_send_is_rate_limited(api):
    from tests.test_email_2fa_captcha import _challenge, _mfa_user

    await _mfa_user(api)
    config = api["config"]
    config.two_factor_email_enabled = True
    config.send_code_rate_limit_email = 2  # 1 already used by the register code
    token = (await _challenge(api))["challenge_token"]
    first = await api["client"].post("/api/auth/login/2fa/email/send", json={"challenge_token": token})
    assert first.status_code == 200
    second = await api["client"].post("/api/auth/login/2fa/email/send", json={"challenge_token": token})
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.parametrize("backend", ["db", "memory"])
async def test_counter_backends(api, backend):
    from account_kit.state import counter_clear, counter_get, counter_hit

    config = api["config"]
    config.state_backend = backend
    async with api["sessions"]() as db:
        assert (await counter_hit(db, config, "k:test", 60))[0] == 1
        count, ttl = await counter_hit(db, config, "k:test", 60)
        assert count == 2 and 0 < ttl <= 60
        assert await counter_get(db, config, "k:test") == 2
        await counter_clear(db, config, "k:test")
        assert await counter_get(db, config, "k:test") == 0
