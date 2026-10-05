"""Regression: UserResponse must accept SQLAlchemy date for birth_year_month."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace

from account_kit.models import User
from account_kit.schemas import UserResponse
from tests.test_auth import _register


def _user_like(**overrides):
    base = dict(
        id=uuid.uuid4(),
        username="birthuser",
        email="birth@example.com",
        full_name=None,
        institution=None,
        gender=None,
        birth_year_month=date(1990, 5, 1),
        role="user",
        is_admin=False,
        is_active=True,
        approval_status="approved",
        has_custom_avatar=False,
        pending_role=None,
        tier=None,
        tier_name=None,
        tier_badge_color=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_user_response_accepts_date_birth_year_month():
    resp = UserResponse.model_validate(_user_like(birth_year_month=date(1990, 5, 1)))
    assert resp.birth_year_month == "1990-05"


def test_user_response_accepts_datetime_birth_year_month():
    resp = UserResponse.model_validate(_user_like(birth_year_month=datetime(1988, 12, 15, 8, 30)))
    assert resp.birth_year_month == "1988-12"


def test_user_response_accepts_string_and_none():
    assert UserResponse.model_validate(_user_like(birth_year_month="2001-03")).birth_year_month == "2001-03"
    assert UserResponse.model_validate(_user_like(birth_year_month=None)).birth_year_month is None


async def test_patch_me_birth_year_month_then_get_me(api):
    user = await _register(api, email="birth-api@example.com", username="birthapi")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "approved"
        await db.commit()
    client = api["client"]
    logged = await client.post("/api/auth/login", data={"username": "birthapi", "password": "secret1"})
    assert logged.status_code == 200, logged.text
    headers = {"Authorization": f"Bearer {logged.json()['access_token']}"}

    patched = await client.patch("/api/auth/me", json={"birth_year_month": "1992-07"}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["user"]["birth_year_month"] == "1992-07"

    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["birth_year_month"] == "1992-07"

    # Direct ORM date must still validate (the original 500 path).
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        assert isinstance(row.birth_year_month, date)
        assert row.birth_year_month == date(1992, 7, 1)
        validated = UserResponse.model_validate(row)
    assert validated.birth_year_month == "1992-07"
