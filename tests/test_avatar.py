import os

from account_kit.config import get_config
from account_kit.models import User
from tests.test_auth import _register


async def _approved_headers(api, email="ava@example.com", username="avatar"):
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    logged = await api["client"].post("/api/auth/login", data={"username": username, "password": "secret1"})
    assert logged.status_code == 200, logged.text
    return user, {"Authorization": f"Bearer {logged.json()['access_token']}"}


def _enable_memory_avatar():
    store = {}

    async def save(user_id, content, content_type, filename):
        key = f"{user_id}.bin"
        store[key] = (bytes(content), content_type or "image/jpeg", filename)
        return key

    async def delete(path):
        store.pop(path, None)

    async def open_avatar(path):
        if path not in store:
            raise FileNotFoundError(path)
        content, media, _filename = store[path]
        return content, media

    config = get_config()
    config.avatar_enabled = True
    config.avatar_save = save
    config.avatar_delete = delete
    config.avatar_open = open_avatar
    return store


async def test_avatar_disabled_returns_501(api):
    _, headers = await _approved_headers(api)
    client = api["client"]
    posted = await client.post(
        "/api/auth/me/avatar",
        files={"file": ("a.jpg", b"not-empty", "image/jpeg")},
        headers=headers,
    )
    assert posted.status_code == 501
    deleted = await client.delete("/api/auth/me/avatar", headers=headers)
    assert deleted.status_code == 501


async def test_avatar_enabled_without_save_returns_501(api):
    _, headers = await _approved_headers(api)
    get_config().avatar_enabled = True
    posted = await api["client"].post(
        "/api/auth/me/avatar",
        files={"file": ("a.jpg", b"not-empty", "image/jpeg")},
        headers=headers,
    )
    assert posted.status_code == 501


async def test_upload_get_delete_avatar(api):
    user, headers = await _approved_headers(api)
    store = _enable_memory_avatar()
    client = api["client"]
    payload = b"fake-jpeg-bytes"

    empty = await client.post(
        "/api/auth/me/avatar",
        files={"file": ("a.jpg", b"", "image/jpeg")},
        headers=headers,
    )
    assert empty.status_code == 400

    uploaded = await client.post(
        "/api/auth/me/avatar",
        files={"file": ("face.jpg", payload, "image/jpeg")},
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["has_custom_avatar"] is True
    assert store[f"{user['id']}.bin"][0] == payload

    fetched = await client.get(f"/api/auth/users/{user['id']}/avatar", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.content == payload
    assert fetched.headers["content-type"].startswith("image/jpeg")

    removed = await client.delete("/api/auth/me/avatar", headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["has_custom_avatar"] is False
    assert store == {}
    missing = await client.get(f"/api/auth/users/{user['id']}/avatar", headers=headers)
    assert missing.status_code == 404


async def test_get_avatar_requires_login(api):
    user, headers = await _approved_headers(api, email="pub@example.com", username="pubava")
    _enable_memory_avatar()
    client = api["client"]
    await client.post(
        "/api/auth/me/avatar",
        files={"file": ("a.jpg", b"xyz", "image/jpeg")},
        headers=headers,
    )
    anon = await client.get(f"/api/auth/users/{user['id']}/avatar")
    assert anon.status_code == 401


async def test_serve_avatar_local_path_fallback(api, tmp_path):
    user, headers = await _approved_headers(api, email="disk@example.com", username="diskava")
    path = tmp_path / "on-disk.jpg"
    path.write_bytes(b"disk-bytes")
    config = get_config()
    config.avatar_enabled = True
    config.avatar_open = None
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.avatar_path = str(path)
        await db.commit()
    fetched = await api["client"].get(f"/api/auth/users/{user['id']}/avatar", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.content == b"disk-bytes"
    assert os.path.isfile(path)
