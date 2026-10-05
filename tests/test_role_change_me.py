from account_kit.config import get_config
from account_kit.models import Role, User
from tests.test_auth import _register


async def _approved_headers(api, email="role@example.com", username="roleuser"):
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        if await db.get(Role, "doctor") is None:
            db.add(Role(code="doctor", name="医生", sort_order=1, allow_register=True))
        await db.commit()
    logged = await api["client"].post("/api/auth/login", data={"username": username, "password": "secret1"})
    assert logged.status_code == 200, logged.text
    return user, {"Authorization": f"Bearer {logged.json()['access_token']}"}


async def test_my_role_change_request_null_then_pending(api):
    user, headers = await _approved_headers(api)
    client = api["client"]
    empty = await client.get("/api/auth/role-change-requests/me", headers=headers)
    assert empty.status_code == 200, empty.text
    assert empty.json() is None

    created = await client.post(
        "/api/auth/role-change-requests",
        json={"requested_role": "doctor"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["from_role"] == "user"
    assert body["to_role"] == "doctor"
    assert body["status"] == "pending"
    assert body["user_id"] == user["id"]

    mine = await client.get("/api/auth/role-change-requests/me", headers=headers)
    assert mine.status_code == 200, mine.text
    got = mine.json()
    assert got["id"] == body["id"]
    assert got["to_role"] == "doctor"
    assert got["status"] == "pending"

    again = await client.post(
        "/api/auth/role-change-requests",
        json={"requested_role": "doctor"},
        headers=headers,
    )
    assert again.status_code == 409


async def test_my_role_change_requires_auth(api):
    res = await api["client"].get("/api/auth/role-change-requests/me")
    assert res.status_code == 401


async def test_my_role_change_disabled(api):
    _, headers = await _approved_headers(api, email="off@example.com", username="roleoff")
    get_config().role_change_enabled = False
    res = await api["client"].get("/api/auth/role-change-requests/me", headers=headers)
    assert res.status_code == 404
    posted = await api["client"].post(
        "/api/auth/role-change-requests",
        json={"requested_role": "doctor"},
        headers=headers,
    )
    assert posted.status_code == 404
