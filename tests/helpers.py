from account_kit.models import User
from tests.test_auth import _register


async def approved_user(api, username="u1", email=None, password="secret1", login=True, **login_extra):
    email = email or f"{username}@example.com"
    user = await _register(api, email=email, username=username)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    if not login:
        return user, None
    res = await api["client"].post(
        "/api/auth/login", data={"username": username, "password": password, "force": "true", **login_extra}
    )
    assert res.status_code == 200, res.text
    return user, res.json()


def bearer(body_or_token):
    token = body_or_token["access_token"] if isinstance(body_or_token, dict) else body_or_token
    return {"Authorization": f"Bearer {token}"}


async def audit_events(api, user_id=None):
    from sqlalchemy import select

    from account_kit.models import AuthAuditLog

    async with api["sessions"]() as db:
        stmt = select(AuthAuditLog).order_by(AuthAuditLog.created_at)
        if user_id:
            stmt = stmt.where(AuthAuditLog.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [row.event for row in rows]
