"""0.2.2 item 2: verified email change."""

from tests.helpers import approved_user, audit_events, bearer


async def _code_for(api, headers, new_email, **extra):
    res = await api["client"].post("/api/auth/me/email/send-code", json={"new_email": new_email, **extra}, headers=headers)
    assert res.status_code == 200, res.text
    mail = api["sent"][-1]
    assert mail["to"] == new_email and mail["purpose"] == "change_email"
    return res.json(), mail["code"]


async def test_patch_me_email_requires_verification(api):
    user, body = await approved_user(api, "em1")
    headers = bearer(body)
    client = api["client"]
    bare = await client.patch("/api/auth/me", json={"email": "new1@example.com"}, headers=headers)
    assert bare.status_code == 400
    assert bare.json()["detail"]["code"] == "EMAIL_VERIFICATION_REQUIRED"
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["email"] == "em1@example.com"

    info, code = await _code_for(api, headers, "new1@example.com")
    assert info["email"] == "ne***@example.com" and info["cooldown"] == 60
    no_pw = await client.patch("/api/auth/me", json={"email": "new1@example.com", "email_code": code}, headers=headers)
    assert no_pw.status_code == 400
    assert no_pw.json()["detail"] == "当前密码错误"
    ok = await client.patch(
        "/api/auth/me",
        json={"email": "new1@example.com", "email_code": code, "current_password": "secret1", "full_name": "N"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["email"] == "new1@example.com"
    assert ok.json()["user"]["full_name"] == "N"
    assert "email_changed" in await audit_events(api, user["id"])


async def test_post_me_email_flow_and_binding(api):
    _u1, b1 = await approved_user(api, "em2")
    _u2, b2 = await approved_user(api, "em3")
    client = api["client"]
    _info, code = await _code_for(api, bearer(b1), "shared@example.com")
    # Another user cannot redeem a code issued to em2 even for the same address.
    stolen = await client.post(
        "/api/auth/me/email",
        json={"new_email": "shared@example.com", "code": code, "password": "secret1"},
        headers=bearer(b2),
    )
    assert stolen.status_code == 400
    again = await client.post("/api/auth/me/email/send-code", json={"new_email": "shared@example.com"}, headers=bearer(b1))
    assert again.status_code == 429
    assert again.json()["detail"]["code"] == "EMAIL_CODE_TOO_FREQUENT"
    ok = await client.post(
        "/api/auth/me/email",
        json={"new_email": "shared@example.com", "code": code, "password": "secret1"},
        headers=bearer(b1),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["email"] == "shared@example.com"
    taken = await client.post("/api/auth/me/email/send-code", json={"new_email": "shared@example.com"}, headers=bearer(b2))
    assert taken.status_code == 400


async def test_send_code_rejects_same_or_wrong_password(api):
    _u, body = await approved_user(api, "em4")
    client = api["client"]
    same = await client.post("/api/auth/me/email/send-code", json={"new_email": "em4@example.com"}, headers=bearer(body))
    assert same.status_code == 400
    bad_pw = await client.post(
        "/api/auth/me/email/send-code", json={"new_email": "x4@example.com", "password": "nope"}, headers=bearer(body)
    )
    assert bad_pw.status_code == 400


async def test_profile_email_change_modes(api):
    _u, body = await approved_user(api, "em5")
    config = api["config"]
    client = api["client"]
    config.profile_email_change = "reject"
    res = await client.patch("/api/auth/me", json={"email": "x5@example.com"}, headers=bearer(body))
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "EMAIL_CHANGE_VIA_ENDPOINT"
    config.profile_email_change = "direct"
    res = await client.patch("/api/auth/me", json={"email": "x5@example.com"}, headers=bearer(body))
    assert res.status_code == 200
    assert res.json()["user"]["email"] == "x5@example.com"


async def test_change_email_without_password_when_disabled(api):
    _u, body = await approved_user(api, "em6")
    api["config"].change_email_require_password = False
    _info, code = await _code_for(api, bearer(body), "x6@example.com")
    res = await api["client"].post("/api/auth/me/email", json={"new_email": "x6@example.com", "code": code}, headers=bearer(body))
    assert res.status_code == 200, res.text
