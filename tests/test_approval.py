"""0.7.0 stage 1A: approval columns, state machine, admin API, notices."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from account_kit import (
    assert_login_allowed,
    count_pending,
    create_user,
    ensure_admin,
    provision_user,
    set_user_approval,
)
from account_kit.config import get_config
from account_kit.emailer import render_notice_email
from account_kit.i18n import AccountError
from account_kit.models import User
from account_kit.schema_setup import upgrade_sql
from tests.conftest import _database_url
from tests.helpers import approved_user, audit_events, bearer, make_admin
from tests.test_auth import _register


def _code(res):
    body = res.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("code") or body.get("code")
    return body.get("code")


async def test_register_pending_blocks_login(api):
    user = await _register(api, email="pend@example.com", username="pend1")
    assert user["approval_status"] == "pending"
    blocked = await api["client"].post("/api/auth/login", data={"username": "pend1", "password": "secret1"})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "ACCOUNT_PENDING"


async def test_dedicated_approval_approve_then_login(api):
    notices = []

    async def notice_mailer(to, purpose, language, context):
        notices.append({"to": to, "purpose": purpose, "language": language, "context": context})

    api["config"].notice_mailer = notice_mailer
    _admin, headers = await make_admin(api, "apprboss")
    user = await _register(api, email="need@example.com", username="need1")
    decided = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "approved"},
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["approval_status"] == "approved"
    assert body["approval_reason"] is None
    assert body["approval_decided_by"] == "admin:apprboss"
    assert body["approved_at"]
    logged = await api["client"].post("/api/auth/login", data={"username": "need1", "password": "secret1"})
    assert logged.status_code == 200, logged.text
    assert any(item["purpose"] == "approval_approved" and item["to"] == "need@example.com" for item in notices)
    assert "admin_user_approved" in await audit_events(api, user["id"])


async def test_dedicated_reject_requires_reason_and_clears_session(api):
    api["config"].refresh_token_enabled = True
    notices = []

    async def notice_mailer(to, purpose, language, context):
        notices.append({"to": to, "purpose": purpose, "language": language, "context": dict(context)})

    api["config"].notice_mailer = notice_mailer
    _admin, headers = await make_admin(api, "rejadmin")
    user, tokens = await approved_user(api, "rejuser")
    missing = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "rejected"},
        headers=headers,
    )
    assert missing.status_code == 400
    assert _code(missing) == "REJECT_REASON_REQUIRED"
    blank = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "rejected", "reason": "   "},
        headers=headers,
    )
    assert blank.status_code == 400
    too_long = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "rejected", "reason": "x" * 501},
        headers=headers,
    )
    assert too_long.status_code == 400
    assert _code(too_long) == "REJECT_REASON_REQUIRED"

    ok = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "rejected", "reason": "材料不完整"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["approval_status"] == "rejected"
    assert body["approval_reason"] == "材料不完整"
    assert body["approval_decided_by"] == "admin:rejadmin"

    me = await api["client"].get("/api/auth/me", headers=bearer(tokens))
    assert me.status_code == 403
    assert me.json()["code"] == "ACCOUNT_REJECTED"
    assert me.json()["params"]["reason"] == "材料不完整"
    assert "材料不完整" in me.json()["detail"]["message"]

    login = await api["client"].post("/api/auth/login", data={"username": "rejuser", "password": "secret1"})
    assert login.status_code == 403
    assert login.json()["code"] == "ACCOUNT_REJECTED"
    assert login.json()["params"]["reason"] == "材料不完整"

    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        assert row.current_session_id is None
        tokens_left = (await db.execute(text("SELECT count(*) FROM auth.refresh_tokens WHERE user_id = :u AND revoked_at IS NULL"), {"u": user["id"]})).scalar()
        assert int(tokens_left or 0) == 0
    assert any(item["purpose"] == "approval_rejected" and item["context"].get("reason") == "材料不完整" for item in notices)
    assert "admin_user_rejected" in await audit_events(api, user["id"])


async def test_generic_patch_reject_without_reason_still_ok(api):
    _admin, headers = await make_admin(api, "compat")
    user, _tokens = await approved_user(api, "compatuser")
    res = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}",
        json={"approval_status": "rejected"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["approval_status"] == "rejected"
    assert res.json().get("approval_reason") in (None, "")


async def test_cannot_revoke_admin_approval(api):
    admin, headers = await make_admin(api, "keepadmin")
    res = await api["client"].patch(
        f"/api/admin/account/users/{admin['id']}/approval",
        json={"status": "rejected", "reason": "nope"},
        headers=headers,
    )
    assert res.status_code == 400
    assert _code(res) == "ADMIN_DEACTIVATE_FORBIDDEN"


async def test_create_user_default_approved_ignores_switch(api):
    api["config"].require_approval = True
    async with api["sessions"]() as db:
        user = await create_user(db, get_config(), username="hostok", email="hostok@example.com", password="secret1")
        assert user.approval_status == "approved"
        assert user.approved_at is not None


async def test_provision_respects_switch_and_admin_source(api):
    notices = []

    async def notice_mailer(to, purpose, language, context):
        notices.append({"to": to, "purpose": purpose, "context": dict(context)})

    api["config"].notice_mailer = notice_mailer
    api["config"].admin_notify_emails = ("ops@example.com",)
    api["config"].require_approval = True
    async with api["sessions"]() as db:
        pending = await provision_user(
            db, get_config(), username="sso1", email="sso1@example.com", source="sso", password_set=False
        )
        assert pending.approval_status == "pending"
        assert pending.approved_at is None
        admin_user = await provision_user(
            db, get_config(), username="adm1", email="adm1@example.com", password="secret1", source="admin"
        )
        assert admin_user.approval_status == "approved"
        api["config"].require_approval = False
        auto = await provision_user(db, get_config(), username="sso2", email="sso2@example.com", source="sso")
        assert auto.approval_status == "approved"
        assert await count_pending(db) == 1
    assert any(item["purpose"] == "admin_pending" and item["to"] == "ops@example.com" for item in notices)
    assert any(item["context"].get("via") == "sso" for item in notices)


async def test_ensure_admin_ignores_require_approval(api):
    api["config"].require_approval = True
    async with api["sessions"]() as db:
        admin = await ensure_admin(db, "root2", "root2@example.com", "secret1", config=get_config())
        assert admin.approval_status == "approved"
        assert admin.is_admin is True


async def test_hot_require_approval_changes_next_register(api):
    api["config"].require_approval = False
    user = await _register(api, email="hot1@example.com", username="hot1")
    assert user["approval_status"] == "approved"
    api["config"].require_approval = True
    other = await _register(api, email="hot2@example.com", username="hot2")
    assert other["approval_status"] == "pending"


async def test_empty_smtp_and_notify_list_register_ok(api):
    api["config"].admin_notify_emails = ()
    api["config"].notice_mailer = None
    api["config"].smtp.host = ""
    api["config"].smtp.user = ""
    api["config"].smtp.password = ""
    user = await _register(api, email="nosmtp@example.com", username="nosmtp")
    assert user["approval_status"] == "pending"


async def test_notice_mailer_failure_is_warning_only(api, caplog):
    async def boom(_to, _purpose, _language, _context):
        raise RuntimeError("smtp down")

    api["config"].notice_mailer = boom
    api["config"].admin_notify_emails = ("ops@example.com",)
    with caplog.at_level("WARNING", logger="account_kit.emailer"):
        user = await _register(api, email="warn@example.com", username="warn1")
    assert user["approval_status"] == "pending"
    assert any("notice mailer failed" in rec.message for rec in caplog.records)


async def test_approved_at_keeps_first_pass(api):
    _admin, headers = await make_admin(api, "firstpass")
    user = await _register(api, email="first@example.com", username="first1")
    first = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "approved"},
        headers=headers,
    )
    assert first.status_code == 200
    stamp = first.json()["approved_at"]
    await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "rejected", "reason": "撤回再审"},
        headers=headers,
    )
    again = await api["client"].patch(
        f"/api/admin/account/users/{user['id']}/approval",
        json={"status": "approved"},
        headers=headers,
    )
    assert again.json()["approved_at"] == stamp
    assert again.json()["approval_reason"] is None


async def test_list_filter_and_pending_count_route_order(api):
    _admin, headers = await make_admin(api, "lister")
    await _register(api, email="p1@example.com", username="listp1")
    await _register(api, email="p2@example.com", username="listp2")
    ok, _ = await approved_user(api, "listok")
    await api["client"].patch(
        f"/api/admin/account/users/{ok['id']}/approval",
        json={"status": "rejected", "reason": "不符合"},
        headers=headers,
    )
    pending = await api["client"].get("/api/admin/account/users", params={"approval_status": "pending"}, headers=headers)
    assert pending.status_code == 200
    names = {row["username"] for row in pending.json()}
    assert "listp1" in names and "listp2" in names
    assert "listok" not in names
    rejected = await api["client"].get(
        "/api/admin/account/users", params={"approval_status": "rejected"}, headers=headers
    )
    assert {row["username"] for row in rejected.json()} == {"listok"}
    bad = await api["client"].get("/api/admin/account/users", params={"approval_status": "nope"}, headers=headers)
    assert bad.status_code == 400
    count = await api["client"].get("/api/admin/account/users/pending-count", headers=headers)
    assert count.status_code == 200, count.text
    assert count.json() == {"pending": 2}


async def test_assert_login_allowed_splits_codes():
    pending = User(is_active=True, approval_status="pending")
    with pytest.raises(AccountError) as pend:
        assert_login_allowed(pending)
    assert pend.value.kit_code == "ACCOUNT_PENDING"
    disabled = User(is_active=False, approval_status="approved")
    with pytest.raises(AccountError) as off:
        assert_login_allowed(disabled)
    assert off.value.kit_code == "USER_DISABLED"
    rejected = User(is_active=True, approval_status="rejected", approval_reason="资料不符")
    with pytest.raises(AccountError) as rej:
        assert_login_allowed(rejected)
    assert rej.value.kit_code == "ACCOUNT_REJECTED"
    assert rej.value.kit_params["reason"] == "资料不符"
    assert_login_allowed(User(is_active=True, approval_status="approved"))


async def test_set_user_approval_library(api):
    async with api["sessions"]() as db:
        user = await create_user(db, get_config(), username="lib1", email="lib1@example.com", password="secret1")
        user.approval_status = "pending"
        user.approved_at = None
        await db.commit()
        await db.refresh(user)
        with pytest.raises(AccountError) as missing:
            await set_user_approval(db, get_config(), user, status="rejected", require_reason=True)
        assert missing.value.kit_code == "REJECT_REASON_REQUIRED"
        decided = await set_user_approval(
            db, get_config(), user, status="rejected", reason="资格不足", decided_by="host:ops"
        )
        assert decided.approval_status == "rejected"
        assert decided.approval_decided_by == "host:ops"
        first = datetime.now(timezone.utc)
        decided.approved_at = first
        await db.commit()
        passed = await set_user_approval(db, get_config(), decided, status="approved", decided_by="host:ops")
        assert passed.approval_status == "approved"
        assert passed.approval_reason is None
        assert passed.approved_at == first


async def test_notice_templates_render():
    from account_kit.config import AccountKitConfig

    config = AccountKitConfig(jwt_secret="x", brand_name="Acme", public_base_url="https://ex.example")
    subject, body = render_notice_email(
        config, "approval_approved", "zh", {"username": "alice", "brand": "Acme", "public_base_url": "https://ex.example"}
    )
    assert "已通过审核" in subject
    assert "alice" in body and "Acme" in body
    subject, body = render_notice_email(
        config, "approval_rejected", "en", {"username": "bob", "reason": "incomplete", "brand": "Acme"}
    )
    assert "not approved" in subject.lower()
    assert "incomplete" in body
    subject, body = render_notice_email(
        config, "admin_pending", "zh", {"username": "c1", "email": "c1@example.com", "via": "sso", "brand": "Acme"}
    )
    assert "待审批" in subject
    assert "c1@example.com" in body and "sso" in body


async def test_upgrade_sql_0_7_0_idempotent_and_bind_tickets():
    from account_kit import ensure_schema

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)

        async def columns(conn, table):
            rows = await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'auth' AND table_name = :t ORDER BY column_name"
                ),
                {"t": table},
            )
            return [tuple(row) for row in rows]

        async with engine.connect() as conn:
            expected_tickets = await columns(conn, "bind_tickets")
            user_cols = {row[0] for row in await columns(conn, "users")}
            assert {"approval_reason", "approval_decided_by", "approval_decided_at"} <= user_cols
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE auth.bind_tickets"))
            await conn.execute(text("ALTER TABLE auth.users DROP COLUMN IF EXISTS approval_reason"))
            await conn.execute(text("ALTER TABLE auth.users DROP COLUMN IF EXISTS approval_decided_by"))
            await conn.execute(text("ALTER TABLE auth.users DROP COLUMN IF EXISTS approval_decided_at"))
        sql = upgrade_sql("0.7.0")
        assert "approval_reason" in sql
        assert "bind_tickets" in sql
        for _ in range(2):
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(sql)
        async with engine.connect() as conn:
            assert await columns(conn, "bind_tickets") == expected_tickets
            user_cols = {row[0] for row in await columns(conn, "users")}
            assert {"approval_reason", "approval_decided_by", "approval_decided_at"} <= user_cols
        await ensure_schema(engine)
    finally:
        await engine.dispose()


async def test_column_upgrades_include_approval_fields():
    from account_kit.schema_setup import _COLUMN_UPGRADES

    joined = "\n".join(_COLUMN_UPGRADES)
    assert "approval_reason" in joined
    assert "approval_decided_by" in joined
    assert "approval_decided_at" in joined


async def test_sso_assert_rejected_code(api):
    from account_kit.sso.service import assert_sso_user

    user, _ = await approved_user(api, "ssorej", login=False)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "rejected"
        row.approval_reason = "身份不符"
        await db.commit()
        await db.refresh(row)
        with pytest.raises(AccountError) as exc:
            assert_sso_user(row)
        assert exc.value.kit_code == "ACCOUNT_REJECTED"
        assert exc.value.kit_params["reason"] == "身份不符"


async def test_sso_assert_pending_code(api):
    from account_kit.sso.service import assert_sso_user

    user = await _register(api, email="ssopend@example.com", username="ssopend")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        with pytest.raises(AccountError) as exc:
            assert_sso_user(row)
        assert exc.value.kit_code == "ACCOUNT_PENDING"


async def test_login_user_tokens_and_me_split_rejected_reason(api):
    from account_kit.service import login_user_tokens

    user, tokens = await approved_user(api, "tokrej")
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.approval_status = "rejected"
        row.approval_reason = "资质不足"
        await db.commit()
        await db.refresh(row)
        with pytest.raises(AccountError) as exc:
            await login_user_tokens(db, get_config(), username="tokrej", password="secret1")
        assert exc.value.kit_code == "ACCOUNT_REJECTED"
        assert exc.value.kit_params["reason"] == "资质不足"
    me = await api["client"].get("/api/auth/me", headers=bearer(tokens))
    assert me.status_code == 403
    assert me.json()["code"] == "ACCOUNT_REJECTED"
    assert me.json()["params"]["reason"] == "资质不足"
    assert "资质不足" in me.json()["detail"]["message"]
