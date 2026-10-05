from account_kit.models import User


async def _register(api, email="user@example.com", username="alice", role=None):
    client = api["client"]
    res = await client.post(
        "/api/auth/send-code",
        json={"email": email, "purpose": "register", "language": "zh"},
    )
    assert res.status_code == 200, res.text
    code = api["sent"][-1]["code"]
    body = {
        "username": username,
        "email": email,
        "password": "secret1",
        "code": code,
        "full_name": "Alice",
    }
    if role:
        body["role"] = role
    created = await client.post("/api/auth/register", json=body)
    assert created.status_code == 200, created.text
    return created.json()


async def test_register_login_and_approval(api):
    user = await _register(api)
    assert user["role"] == "user"
    assert user["is_admin"] is False
    assert user["approval_status"] == "pending"
    assert user["tier"] == "free"

    blocked = await api["client"].post("/api/auth/login", data={"username": "alice", "password": "secret1"})
    assert blocked.status_code == 403

    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        row.is_admin = True
        await db.commit()

    logged = await api["client"].post("/api/auth/login", data={"username": "alice", "password": "secret1"})
    assert logged.status_code == 200, logged.text
    token = logged.json()["access_token"]
    me = await api["client"].get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["is_admin"] is True
    assert me.json()["tier"] == "free"


async def test_admin_is_a_flag_not_a_role(api):
    user = await _register(api)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        row.is_admin = True
        await db.commit()
    logged = await api["client"].post("/api/auth/login", data={"username": "alice", "password": "secret1"})
    headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}

    rejected = await api["client"].post(
        "/api/admin/account/roles",
        json={"code": "admin", "name": "管理员"},
        headers=headers,
    )
    assert rejected.status_code == 400

    created = await api["client"].post(
        "/api/admin/account/roles",
        json={"code": "doctor", "name": "医生", "allow_register": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}",
        json={"role": "doctor", "is_admin": True, "tier_code": "pro"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["role"] == "doctor"
    assert body["is_admin"] is True
    assert body["tier"] == "pro"

    custom = await api["client"].post(
        "/api/admin/account/tiers",
        json={"code": "plus", "name": "Plus", "badge_color": "#52c41a"},
        headers=headers,
    )
    assert custom.status_code == 201, custom.text
    moved = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}",
        json={"tier_code": "plus"},
        headers=headers,
    )
    assert moved.json()["tier"] == "plus"
    blocked = await api["client"].delete("/api/admin/account/tiers/plus", headers=headers)
    assert blocked.status_code == 409


async def test_single_device_session(api):
    user = await _register(api, email="bob@example.com", username="bob")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    first = await api["client"].post(
        "/api/auth/login",
        data={"username": "bob", "password": "secret1", "device_name": "pc"},
    )
    assert first.status_code == 200, first.text
    second = await api["client"].post(
        "/api/auth/login",
        data={"username": "bob", "password": "secret1", "device_name": "phone"},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ALREADY_LOGGED_IN"
    forced = await api["client"].post(
        "/api/auth/login",
        data={"username": "bob", "password": "secret1", "force": "true", "device_name": "phone"},
    )
    assert forced.status_code == 200, forced.text
    stale = await api["client"].get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {first.json()['access_token']}"},
    )
    assert stale.status_code == 401
