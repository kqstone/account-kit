"""i18n: catalogs, negotiation, response shape, email language, overrides."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from account_kit import init_db, mount_account
from account_kit.config import AccountKitConfig, set_config
from account_kit.i18n import (
    DEFAULT_LOCALE,
    MESSAGES,
    SESSION_REPLACED,
    canonicalize_locale,
    normalize_locale,
    t,
)
from account_kit.i18n.messages import SUPPORTED_LOCALES
from tests.helpers import approved_user

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "account_kit"

_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII_SENTENCE = re.compile(r"[A-Za-z]{3,}\s+[A-Za-z]")


def test_catalogs_identical_keys():
    zh = MESSAGES["zh-CN"]
    en = MESSAGES["en"]
    assert set(zh) == set(en)
    assert SUPPORTED_LOCALES == ("zh-CN", "en")
    assert DEFAULT_LOCALE == "zh-CN"


def test_normalize_and_canonicalize():
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh_CN") == "zh-CN"
    assert normalize_locale("zh-cn") == "zh-CN"
    assert normalize_locale("zh-Hans") == "zh-CN"
    assert normalize_locale("zh-TW") == "zh-CN"
    assert normalize_locale("en") == "en"
    assert normalize_locale("en-US") == "en"
    assert canonicalize_locale("fr") == "zh-CN"
    assert canonicalize_locale("pt-BR") == "zh-CN"
    assert canonicalize_locale("") == "zh-CN"


def _codes_in_source() -> set[str]:
    codes: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "messages.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name not in {"account_error", "_err", "AdminSetupError", "refresh_error"}:
                continue
            args = list(node.args)
            if name == "account_error" and len(args) >= 2 and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
                codes.add(args[1].value)
            elif name in {"_err", "AdminSetupError", "refresh_error"} and args:
                idx = 1 if name == "_err" and len(args) >= 2 else 0
                arg = args[idx]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.isupper():
                    codes.add(arg.value)
            for kw in node.keywords:
                if kw.arg in {"code", "message_key"} and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    codes.add(kw.value.value)
    codes.add("VALIDATION_ERROR")
    return codes


def test_every_used_code_exists_in_catalogs():
    used = _codes_in_source()
    assert used
    missing_zh = sorted(used - set(MESSAGES["zh-CN"]))
    missing_en = sorted(used - set(MESSAGES["en"]))
    assert missing_zh == []
    assert missing_en == []


def test_zh_cn_has_no_ascii_only_english_sentences():
    allowed_exact = {SESSION_REPLACED}
    for key, text in MESSAGES["zh-CN"].items():
        if text in allowed_exact:
            continue
        if _CJK.search(text):
            continue
        if "pip install" in text or "Pillow" in text:
            continue
        if "{" in text:
            continue
        assert not _ASCII_SENTENCE.search(text), f"{key}: {text!r}"


def test_en_has_no_cjk():
    for key, text in MESSAGES["en"].items():
        assert not _CJK.search(text), f"{key}: {text!r}"


async def test_default_login_fail_is_chinese(api):
    await approved_user(api, username="loc1", login=False)
    res = await api["client"].post("/api/auth/login", data={"username": "loc1", "password": "wrong"})
    assert res.status_code == 401
    body = res.json()
    assert body["detail"] == "用户名或密码错误"
    assert isinstance(body["detail"], str)
    assert body["code"] == "INVALID_CREDENTIALS"


async def test_x_locale_en_login_fail(api):
    await approved_user(api, username="loc2", login=False)
    res = await api["client"].post(
        "/api/auth/login",
        data={"username": "loc2", "password": "wrong"},
        headers={"X-Locale": "en"},
    )
    assert res.status_code == 401
    body = res.json()
    assert body["detail"] == "Incorrect username or password"
    assert body["code"] == "INVALID_CREDENTIALS"


async def test_dict_error_keeps_extra_fields(api):
    api["config"].captcha_verifier = lambda *_a, **_k: True
    api["config"].captcha_fail_threshold = 1
    await approved_user(api, username="loc3", login=False)
    await api["client"].post("/api/auth/login", data={"username": "loc3", "password": "wrong"})
    res = await api["client"].post("/api/auth/login", data={"username": "loc3", "password": "wrong"})
    assert res.status_code == 428
    body = res.json()
    assert body["code"] == "CAPTCHA_REQUIRED"
    assert body["detail"]["code"] == "CAPTCHA_REQUIRED"
    assert body["detail"]["captcha_required"] is True
    assert "message" in body["detail"]


async def test_session_replaced_literal(api):
    api["config"].session_mode = "single_device"
    _user, body = await approved_user(api, username="loc4")
    token = body["access_token"]
    await api["client"].post(
        "/api/auth/login", data={"username": "loc4", "password": "secret1", "force": "true"}
    )
    me = await api["client"].get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
    assert me.json()["detail"] == "SESSION_REPLACED"
    assert me.json()["code"] == "SESSION_REPLACED"
    en = await api["client"].get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}", "X-Locale": "en"}
    )
    assert en.json()["detail"] == "SESSION_REPLACED"


async def test_negotiation_order(api):
    await approved_user(api, username="neg1", login=False)
    config = api["config"]
    client = api["client"]

    async def login(**kwargs):
        return await client.post("/api/auth/login", data={"username": "neg1", "password": "x"}, **kwargs)

    config.negotiate_accept_language = True
    accept = await login(headers={"Accept-Language": "en-US,en;q=0.9"})
    assert accept.json()["detail"] == "Incorrect username or password"

    query = await login(params={"locale": "zh-CN"}, headers={"Accept-Language": "en"})
    assert query.json()["detail"] == "用户名或密码错误"

    header = await login(
        params={"locale": "en"},
        headers={"X-Locale": "zh", "Accept-Language": "en"},
    )
    assert header.json()["detail"] == "用户名或密码错误"

    config.locale_resolver = lambda _req: "en"
    resolver = await login(headers={"X-Locale": "zh-CN"})
    assert resolver.json()["detail"] == "Incorrect username or password"
    config.locale_resolver = None
    config.negotiate_accept_language = False


async def test_unsupported_locale_falls_back(api):
    await approved_user(api, username="fb1", login=False)
    res = await api["client"].post(
        "/api/auth/login",
        data={"username": "fb1", "password": "x"},
        headers={"X-Locale": "fr-FR"},
    )
    assert res.json()["detail"] == "用户名或密码错误"


async def test_captcha_threshold_still_works_in_en(api):
    checked = []

    async def verify(captcha_id, captcha_code):
        checked.append((captcha_id, captcha_code))
        return captcha_id == "cid" and captcha_code == "ABCD"

    api["config"].captcha_verifier = verify
    api["config"].captcha_fail_threshold = 2
    await approved_user(api, username="capen", login=False)
    headers = {"X-Locale": "en"}
    first = await api["client"].post(
        "/api/auth/login", data={"username": "capen", "password": "bad"}, headers=headers
    )
    assert first.status_code == 401
    assert first.json()["detail"]["message"] == "Incorrect username or password"
    second = await api["client"].post(
        "/api/auth/login", data={"username": "capen", "password": "bad"}, headers=headers
    )
    assert second.json()["detail"]["captcha_required"] is True
    need = await api["client"].post(
        "/api/auth/login", data={"username": "capen", "password": "secret1"}, headers=headers
    )
    assert need.status_code == 428
    assert need.json()["code"] == "CAPTCHA_REQUIRED"
    assert need.json()["detail"]["message"] == "Captcha required"


async def test_email_language_explicit_and_request_locale(api):
    sent = api["sent"]
    await api["client"].post(
        "/api/auth/send-code",
        json={"email": "a@example.com", "purpose": "register", "language": "en"},
    )
    assert sent[-1]["language"] == "en"
    await api["client"].post(
        "/api/auth/send-code",
        json={"email": "b@example.com", "purpose": "register"},
        headers={"X-Locale": "en"},
    )
    assert sent[-1]["language"] == "en"
    await api["client"].post(
        "/api/auth/send-code",
        json={"email": "c@example.com", "purpose": "register"},
    )
    assert sent[-1]["language"] == "zh"


async def test_messages_override(api):
    api["config"].messages_override = {"zh-CN": {"INVALID_CREDENTIALS": "自定义登录失败"}}
    await approved_user(api, username="ov1", login=False)
    res = await api["client"].post("/api/auth/login", data={"username": "ov1", "password": "x"})
    assert res.json()["detail"] == "自定义登录失败"
    api["config"].messages_override = None


async def test_host_http_exception_untouched():
    url = os.environ.get("ACCOUNT_KIT_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("ACCOUNT_KIT_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    await init_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def get_db():
        async with sessions() as session:
            yield session

    config = AccountKitConfig(jwt_secret="host-exc", state_backend="memory")
    app = FastAPI()

    @app.get("/host-plain")
    async def host_plain():
        raise HTTPException(status_code=418, detail="teapot from host")

    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/host-plain")
        assert res.status_code == 418
        assert res.json() == {"detail": "teapot from host"}
        assert "code" not in res.json()
    await engine.dispose()
    set_config(AccountKitConfig(jwt_secret="test-secret"))


async def test_login_failed_audit_reason_uses_error_code(api):
    import json

    from sqlalchemy import select

    from account_kit.models import AuthAuditLog, User

    await approved_user(api, username="audr1", login=False)
    bad = await api["client"].post(
        "/api/auth/login",
        data={"username": "audr1", "password": "wrong"},
        headers={"X-Locale": "zh-CN"},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "用户名或密码错误"
    assert bad.json()["code"] == "INVALID_CREDENTIALS"

    en_bad = await api["client"].post(
        "/api/auth/login",
        data={"username": "audr1", "password": "wrong"},
        headers={"X-Locale": "en"},
    )
    assert en_bad.status_code == 401
    assert en_bad.json()["detail"] == "Incorrect username or password"

    user, _ = await approved_user(api, username="audr2", login=False)
    async with api["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.is_active = False
        await db.commit()
    disabled = await api["client"].post(
        "/api/auth/login",
        data={"username": "audr2", "password": "secret1"},
        headers={"X-Locale": "zh-CN"},
    )
    assert disabled.status_code == 403
    assert disabled.json()["code"] == "USER_DISABLED"
    assert disabled.json()["detail"] == "账号已被停用"

    async with api["sessions"]() as db:
        rows = (await db.execute(select(AuthAuditLog).where(AuthAuditLog.event == "login_failed"))).scalars().all()
        by_user: dict[str, list[str]] = {}
        for row in rows:
            if not row.meta:
                continue
            meta = json.loads(row.meta)
            name = meta.get("username")
            reason = meta.get("reason")
            if name and reason:
                by_user.setdefault(name, []).append(reason)

    assert by_user["audr1"]
    assert all(reason == "invalid_credentials" for reason in by_user["audr1"])
    assert "用户名或密码错误" not in by_user["audr1"]
    assert "Incorrect username or password" not in by_user["audr1"]
    assert by_user["audr2"] == ["USER_DISABLED"]
    assert by_user["audr2"][0] != disabled.json()["detail"]


def test_t_override_and_params():
    set_config(
        AccountKitConfig(
            jwt_secret="x",
            messages_override={"en": {"EMAIL_DOMAIN_NOT_ALLOWED": "only {allowed}"}},
        )
    )
    assert t("EMAIL_DOMAIN_NOT_ALLOWED", {"allowed": "a.com"}, locale="en") == "only a.com"
    set_config(AccountKitConfig(jwt_secret="x"))
