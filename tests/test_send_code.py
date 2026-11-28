"""Send-code feedback: honest errors, 120s resend interval, invalid email, old-code invalidation."""

from tests.helpers import approved_user, bearer, make_admin
from tests.test_otp_limits import _send


async def test_send_code_success_includes_cooldown_and_expires_in(api):
    res = await _send(api, "ok@example.com", "register")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "success"
    assert body["detail"] == "验证码已发送"
    assert body["cooldown"] == 120
    assert body["expires_in"] == 300
    verified = await api["client"].post(
        "/api/auth/verify-code",
        json={"email": "ok@example.com", "purpose": "register", "code": api["sent"][-1]["code"]},
    )
    assert verified.status_code == 200
    assert "cooldown" not in verified.json()


async def test_register_taken_email_is_400_and_does_not_send(api):
    await approved_user(api, "taken", login=False)
    before = len(api["sent"])
    res = await _send(api, "taken@example.com", "register")
    assert res.status_code == 400
    assert res.json()["code"] == "EMAIL_TAKEN"
    assert res.json()["detail"] == "该邮箱已注册"
    assert len(api["sent"]) == before


async def test_reset_unregistered_is_404_and_does_not_send(api):
    before = len(api["sent"])
    res = await _send(api, "nobody@example.com", "reset_password")
    assert res.status_code == 404
    assert res.json()["code"] == "EMAIL_NOT_REGISTERED"
    assert res.json()["detail"] == "该邮箱未注册账号"
    assert len(api["sent"]) == before


async def test_admin_public_reset_not_allowed(api):
    user, _headers = await make_admin(api, "boss")
    before = len(api["sent"])
    res = await _send(api, user["email"], "reset_password")
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "PASSWORD_RESET_NOT_ALLOWED"
    assert body["detail"] == "该账号不支持通过此方式重置密码"
    assert "管理员" not in body["detail"]
    assert "admin" not in body["detail"].lower()
    assert len(api["sent"]) == before
    en = await api["client"].post(
        "/api/auth/send-code",
        json={"email": user["email"], "purpose": "reset_password"},
        headers={"X-Locale": "en"},
    )
    assert en.status_code == 400
    assert en.json()["code"] == "PASSWORD_RESET_NOT_ALLOWED"
    assert "admin" not in en.json()["detail"].lower()
    assert "管理员" not in en.json()["detail"]


async def test_email_code_too_frequent_has_retry_after(api):
    first = await _send(api, "freq@example.com", "register")
    assert first.status_code == 200
    again = await _send(api, "freq@example.com", "register")
    assert again.status_code == 429
    detail = again.json()["detail"]
    assert detail["code"] == "EMAIL_CODE_TOO_FREQUENT"
    assert 1 <= detail["retry_after"] <= 120
    assert again.headers.get("retry-after") == str(detail["retry_after"])


async def test_new_code_invalidates_previous_unused_code(api):
    api["config"].otp_resend_window_seconds = 0
    first = await _send(api, "reuse@example.com", "register")
    assert first.status_code == 200
    code1 = api["sent"][-1]["code"]
    second = await _send(api, "reuse@example.com", "register")
    assert second.status_code == 200
    code2 = api["sent"][-1]["code"]
    assert code1 != code2
    stale = await api["client"].post(
        "/api/auth/verify-code",
        json={"email": "reuse@example.com", "purpose": "register", "code": code1},
    )
    assert stale.status_code == 400
    assert stale.json()["code"] == "CODE_INVALID"
    fresh = await api["client"].post(
        "/api/auth/verify-code",
        json={"email": "reuse@example.com", "purpose": "register", "code": code2},
    )
    assert fresh.status_code == 200


async def test_invalid_or_empty_email_is_email_invalid_not_422(api):
    client = api["client"]
    for payload in (
        {"email": "", "purpose": "register"},
        {"email": "not-an-email", "purpose": "register"},
        {"email": "nodot@localhost", "purpose": "register"},
        {"email": "user@", "purpose": "register"},
    ):
        res = await client.post("/api/auth/send-code", json=payload)
        assert res.status_code == 400, payload
        assert res.json()["code"] == "EMAIL_INVALID"
    _u, body = await approved_user(api, "inv")
    bad = await client.post(
        "/api/auth/me/email/send-code", json={"new_email": "bad-email"}, headers=bearer(body)
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "EMAIL_INVALID"
    empty = await client.post(
        "/api/auth/me/email/send-code", json={"new_email": ""}, headers=bearer(body)
    )
    assert empty.status_code == 400
    assert empty.json()["code"] == "EMAIL_INVALID"


async def test_register_domain_not_allowed_before_guard_send(api):
    config = api["config"]
    config.email_domain_restriction = True
    config.allowed_email_domains = ("allowed.com",)
    config.send_code_rate_limit_email = 1
    config.send_code_rate_limit_ip = 1
    for _ in range(3):
        res = await _send(api, "user@blocked.com", "register")
        assert res.status_code == 400
        assert res.json()["code"] == "EMAIL_DOMAIN_NOT_ALLOWED"
    ok = await _send(api, "user@allowed.com", "register")
    assert ok.status_code == 200, ok.text


async def test_register_taken_still_counts_guard_send(api):
    await approved_user(api, "lim", login=False)
    api["config"].send_code_rate_limit_email = 2
    taken = await _send(api, "lim@example.com", "register")
    assert taken.status_code == 400
    assert taken.json()["code"] == "EMAIL_TAKEN"
    blocked = await _send(api, "lim@example.com", "register")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


async def test_reset_unregistered_still_counts_guard_send(api):
    api["config"].send_code_rate_limit_email = 2
    first = await _send(api, "ghost@example.com", "reset_password")
    assert first.status_code == 404
    second = await _send(api, "ghost@example.com", "reset_password")
    assert second.status_code == 404
    third = await _send(api, "ghost@example.com", "reset_password")
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "RATE_LIMITED"


async def test_admin_reset_still_counts_guard_send(api):
    user, _headers = await make_admin(api, "adm2")
    api["config"].send_code_rate_limit_email = 2
    first = await _send(api, user["email"], "reset_password")
    assert first.status_code == 400
    assert first.json()["code"] == "PASSWORD_RESET_NOT_ALLOWED"
    blocked = await _send(api, user["email"], "reset_password")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"
