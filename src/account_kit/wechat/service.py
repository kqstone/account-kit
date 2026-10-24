"""WeChat Mini Program QR login: tickets, bindings, and token hand-off."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import audit as audit_mod
from account_kit.audit import audit, request_ip
from account_kit.config import AccountKitConfig
from account_kit.crypto import fernet_for
from account_kit.i18n import account_error
from account_kit.models import User, WechatIdentity, WechatLoginTicket
from account_kit.otp import run_before_action
from account_kit.schemas import RegisterRequest
from account_kit.security import verify_password
from account_kit.service import (
    complete_login_tokens,
    get_user_by_id,
    get_user_by_username,
    register_user,
    sanitize_device_name,
)
from account_kit.state import enforce_limit
from account_kit.wechat import wxapi

SCENE_ALPHABET = string.ascii_letters + string.digits
OPEN_STATUSES = ("pending", "scanned", "unbound", "confirmed")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def app_id_of(config: AccountKitConfig) -> str:
    return (config.wechat_app_id or "").strip() or "test"


def qr_configured(config: AccountKitConfig) -> bool:
    if config.wechat_get_wxacode is not None:
        return True
    return bool((config.wechat_app_id or "").strip() and (config.wechat_app_secret or "").strip())


def session_configured(config: AccountKitConfig) -> bool:
    if config.wechat_code2session is not None:
        return True
    return bool((config.wechat_app_id or "").strip() and (config.wechat_app_secret or "").strip())


def require_qr_configured(config: AccountKitConfig) -> None:
    if not qr_configured(config):
        raise account_error(503, "WECHAT_NOT_CONFIGURED")


def require_session_configured(config: AccountKitConfig) -> None:
    if not session_configured(config):
        raise account_error(503, "WECHAT_NOT_CONFIGURED")


def ticket_hash(raw: str) -> str:
    return hashlib.sha256(("wechat-ticket:" + (raw or "")).encode("utf-8")).hexdigest()


def openid_digest(app_id: str, openid: str) -> str:
    return hashlib.sha256(("wechat-openid:" + app_id + ":" + (openid or "")).encode("utf-8")).hexdigest()


def access_token_digest(raw: str) -> str:
    return hashlib.sha256(("wechat-token:" + (raw or "")).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def expires_in(ticket: WechatLoginTicket) -> int:
    exp = _aware(ticket.expires_at)
    if exp is None:
        return 0
    return max(0, int((exp - _now()).total_seconds()))


def encrypt_payload(config: AccountKitConfig, payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return fernet_for(config.encryption_material()).encrypt(raw).decode("ascii")


def decrypt_payload(config: AccountKitConfig, cipher: Optional[str]) -> Dict[str, Any]:
    if not cipher:
        return {}
    raw = fernet_for(config.encryption_material()).decrypt(cipher.encode("ascii"))
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def mask_openid(openid: str) -> str:
    text = openid or ""
    if len(text) <= 8:
        return (text[:2] + "****") if text else ""
    return text[:4] + "****" + text[-4:]


def image_mime(data: bytes) -> str:
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"


def env_version_of(config: AccountKitConfig) -> str:
    value = (config.wechat_env_version or "release").strip().lower()
    if value not in ("release", "trial", "develop"):
        return "release"
    return value


async def wechat_ip_limit(db: AsyncSession, config: AccountKitConfig, request) -> None:
    ip = request_ip(config, request)
    window = int(config.login_rate_window_seconds or 60) or 60
    if ip:
        await enforce_limit(db, config, f"wechat:ip:{ip}", config.wechat_login_rate_limit_ip, window)


async def _awaitable(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def exchange_js_code(config: AccountKitConfig, js_code: str) -> Tuple[str, Optional[str]]:
    require_session_configured(config)
    code = (js_code or "").strip()
    if not code:
        raise account_error(401, "WECHAT_CODE_INVALID")
    if config.wechat_code2session is not None:
        payload = await _awaitable(config.wechat_code2session(code))
    else:
        payload = await wxapi.code2session(config.wechat_app_id, config.wechat_app_secret, code)
    if not isinstance(payload, dict):
        raise account_error(401, "WECHAT_CODE_INVALID")
    openid = str(payload.get("openid") or "").strip()
    if not openid:
        raise account_error(401, "WECHAT_CODE_INVALID")
    unionid = str(payload.get("unionid") or "").strip() or None
    return openid, unionid


async def fetch_wxacode(config: AccountKitConfig, scene: str, page: str) -> bytes:
    require_qr_configured(config)
    env = env_version_of(config)
    check_path = bool(config.wechat_check_path)
    if config.wechat_get_wxacode is not None:
        data = await _awaitable(config.wechat_get_wxacode(scene, page, env, check_path, 280))
    else:
        data = await wxapi.get_wxacode_unlimit(
            config.wechat_app_id,
            config.wechat_app_secret,
            scene=scene,
            page=page,
            env_version=env,
            check_path=check_path,
            width=280,
        )
    if not data or not isinstance(data, (bytes, bytearray)):
        raise account_error(502, "WECHAT_QR_FAILED")
    return bytes(data)


def new_scene() -> str:
    return "".join(secrets.choice(SCENE_ALPHABET) for _ in range(16))


def new_ticket_raw() -> str:
    return secrets.token_urlsafe(32)


async def get_identity_by_openid(db: AsyncSession, app_id: str, openid: str) -> Optional[WechatIdentity]:
    result = await db.execute(
        select(WechatIdentity).where(WechatIdentity.app_id == app_id, WechatIdentity.openid == openid)
    )
    return result.scalars().first()


async def get_identity_by_user(db: AsyncSession, user_id, app_id: str) -> Optional[WechatIdentity]:
    result = await db.execute(
        select(WechatIdentity).where(WechatIdentity.user_id == user_id, WechatIdentity.app_id == app_id)
    )
    return result.scalars().first()


async def load_ticket_by_raw(db: AsyncSession, raw: Optional[str], *, touch_expiry: bool = True) -> WechatLoginTicket:
    """Web clients send the opaque ticket; the Mini Program sends ``scene`` in the same field."""
    if not raw or len(raw) > 256:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    value = raw.strip()
    result = await db.execute(select(WechatLoginTicket).where(WechatLoginTicket.ticket_hash == ticket_hash(value)))
    row = result.scalars().first()
    if row is None and len(value) <= 32 and all(ch in SCENE_ALPHABET for ch in value):
        result = await db.execute(select(WechatLoginTicket).where(WechatLoginTicket.scene == value))
        row = result.scalars().first()
    if row is None:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    return await refresh_ticket_status(db, row, touch_expiry=touch_expiry)


async def refresh_ticket_status(db: AsyncSession, ticket: WechatLoginTicket, *, touch_expiry: bool = True) -> WechatLoginTicket:
    if ticket.status in OPEN_STATUSES and touch_expiry:
        exp = _aware(ticket.expires_at)
        if exp is not None and exp <= _now():
            ticket.status = "expired"
            ticket.payload_cipher = None
            await db.commit()
            await db.refresh(ticket)
    return ticket


def assert_usable(ticket: WechatLoginTicket, *, allow: Tuple[str, ...] = OPEN_STATUSES) -> None:
    if ticket.status == "expired":
        raise account_error(400, "WECHAT_TICKET_EXPIRED")
    if ticket.status == "consumed":
        raise account_error(400, "WECHAT_TICKET_CONSUMED")
    if ticket.status == "cancelled":
        raise account_error(400, "WECHAT_TICKET_INVALID")
    if ticket.status not in allow:
        raise account_error(400, "WECHAT_TICKET_INVALID")


async def create_ticket(
    db: AsyncSession,
    config: AccountKitConfig,
    *,
    purpose: str,
    request,
    device_name: str = "",
    force: bool = False,
    user_id=None,
) -> Tuple[WechatLoginTicket, str, str]:
    ttl = max(30, int(config.wechat_qr_ttl_seconds or 120))
    raw = new_ticket_raw()
    scene = new_scene()
    for _ in range(6):
        exists = await db.execute(select(WechatLoginTicket.id).where(WechatLoginTicket.scene == scene))
        if exists.scalar() is None:
            break
        scene = new_scene()
    row = WechatLoginTicket(
        ticket_hash=ticket_hash(raw),
        scene=scene,
        purpose=purpose,
        status="pending",
        user_id=user_id,
        created_ip=(request_ip(config, request) or "")[:64] or None,
        device_name=sanitize_device_name(device_name)[:128],
        force=bool(force),
        expires_at=_now() + timedelta(seconds=ttl),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, raw, scene


async def start_login(db: AsyncSession, config: AccountKitConfig, request, *, device_name: str = "", force: bool = False) -> dict:
    require_qr_configured(config)
    await run_before_action(config, request, "wechat_start", {"purpose": "login"})
    await wechat_ip_limit(db, config, request)
    page = (config.wechat_qr_page or "pages/login/confirm").strip() or "pages/login/confirm"
    _row, raw, scene = await create_ticket(
        db, config, purpose="login", request=request, device_name=device_name, force=force
    )
    image = await fetch_wxacode(config, scene, page)
    return {
        "ticket": raw,
        "scene": scene,
        "expires_in": int(config.wechat_qr_ttl_seconds or 120),
        "image_base64": base64.b64encode(image).decode("ascii"),
        "mime": image_mime(image),
    }


async def start_bind(db: AsyncSession, config: AccountKitConfig, request, user: User) -> dict:
    require_qr_configured(config)
    await run_before_action(config, request, "wechat_start", {"purpose": "bind", "user": user})
    await wechat_ip_limit(db, config, request)
    existing = await get_identity_by_user(db, user.id, app_id_of(config))
    if existing is not None:
        raise account_error(409, "WECHAT_BIND_EXISTS")
    page = (config.wechat_bind_page or config.wechat_qr_page or "pages/login/confirm").strip() or "pages/login/confirm"
    _row, raw, scene = await create_ticket(
        db, config, purpose="bind", request=request, device_name="", force=False, user_id=user.id
    )
    image = await fetch_wxacode(config, scene, page)
    return {
        "ticket": raw,
        "scene": scene,
        "expires_in": int(config.wechat_qr_ttl_seconds or 120),
        "image_base64": base64.b64encode(image).decode("ascii"),
        "mime": image_mime(image),
    }


def _store_openid(config: AccountKitConfig, ticket: WechatLoginTicket, openid: str, unionid: Optional[str]) -> None:
    ticket.openid_hash = openid_digest(app_id_of(config), openid)
    ticket.payload_cipher = encrypt_payload(config, {"openid": openid, "unionid": unionid})


def _load_openid(config: AccountKitConfig, ticket: WechatLoginTicket) -> Tuple[str, Optional[str]]:
    data = decrypt_payload(config, ticket.payload_cipher)
    openid = str(data.get("openid") or "").strip()
    if not openid:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    unionid = str(data.get("unionid") or "").strip() or None
    return openid, unionid


async def login_status(db: AsyncSession, config: AccountKitConfig, raw: Optional[str]) -> dict:
    from account_kit.i18n import AccountError

    try:
        ticket = await load_ticket_by_raw(db, raw)
    except AccountError:
        return {"status": "expired"}
    status = ticket.status
    if status in ("pending",):
        return {"status": "pending", "expires_in": expires_in(ticket)}
    if status == "scanned":
        body: Dict[str, Any] = {"status": "scanned", "expires_in": expires_in(ticket)}
        if ticket.user_id:
            user = await get_user_by_id(db, ticket.user_id)
            if user is not None:
                body["username"] = user.username
        return body
    if status == "unbound":
        return {"status": "unbound", "bind_ticket": raw.strip(), "expires_in": expires_in(ticket)}
    if status == "confirmed":
        payload = decrypt_payload(config, ticket.payload_cipher)
        ticket.status = "consumed"
        ticket.consumed_at = _now()
        ticket.payload_cipher = None
        await db.commit()
        body = {"status": "confirmed", "expires_in": 0}
        if payload.get("access_token"):
            body.update({k: v for k, v in payload.items() if k in ("access_token", "token_type", "refresh_token", "refresh_expires_in")})
        return body
    if status == "consumed":
        return {"status": "consumed"}
    if status == "cancelled":
        return {"status": "cancelled"}
    return {"status": "expired"}


async def cancel_ticket(db: AsyncSession, config: AccountKitConfig, raw: Optional[str]) -> dict:
    if not raw:
        return {"status": "cancelled"}
    result = await db.execute(select(WechatLoginTicket).where(WechatLoginTicket.ticket_hash == ticket_hash(raw.strip())))
    ticket = result.scalars().first()
    if ticket is None:
        return {"status": "cancelled"}
    if ticket.status in OPEN_STATUSES:
        ticket.status = "cancelled"
        ticket.payload_cipher = None
        ticket.mfa_challenge_hash = None
        await db.commit()
    return {"status": "cancelled"}


async def scan_login(db: AsyncSession, config: AccountKitConfig, request, *, ticket_raw: str, js_code: str) -> dict:
    require_session_configured(config)
    await wechat_ip_limit(db, config, request)
    openid, unionid = await exchange_js_code(config, js_code)
    ticket = await load_ticket_by_raw(db, ticket_raw)
    if ticket.purpose == "bind":
        # Purpose is derived from the ticket; a client-sent ``purpose`` is ignored.
        assert_usable(ticket, allow=("pending", "scanned"))
        if not ticket.user_id:
            raise account_error(400, "WECHAT_TICKET_INVALID")
        bind_user = await get_user_by_id(db, ticket.user_id)
        if bind_user is None:
            raise account_error(400, "WECHAT_TICKET_INVALID")
        ticket.status = "scanned"
        await db.commit()
        return {"status": "scanned", "purpose": "bind", "username": bind_user.username}
    if ticket.purpose != "login":
        raise account_error(400, "WECHAT_TICKET_INVALID")
    assert_usable(ticket, allow=("pending", "scanned", "unbound"))
    digest = openid_digest(app_id_of(config), openid)
    if ticket.openid_hash and ticket.openid_hash != digest:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    identity = await get_identity_by_openid(db, app_id_of(config), openid)
    _store_openid(config, ticket, openid, unionid)
    if identity is None:
        ticket.status = "unbound"
        ticket.user_id = None
        await db.commit()
        return {"status": "unbound", "purpose": "login"}
    user = await get_user_by_id(db, identity.user_id)
    if user is None:
        ticket.status = "unbound"
        ticket.user_id = None
        await db.commit()
        return {"status": "unbound", "purpose": "login"}
    ticket.status = "scanned"
    ticket.user_id = user.id
    await db.commit()
    return {"status": "scanned", "purpose": "login", "username": user.username}


async def confirm_login(db: AsyncSession, config: AccountKitConfig, request, *, ticket_raw: str, js_code: str, force: bool = False) -> dict:
    require_session_configured(config)
    peek = await load_ticket_by_raw(db, ticket_raw)
    if peek.purpose == "bind":
        return await confirm_bind(db, config, request, ticket_raw=ticket_raw, js_code=js_code)
    await run_before_action(config, request, "wechat_confirm", {"purpose": "login"})
    await wechat_ip_limit(db, config, request)
    openid, _unionid = await exchange_js_code(config, js_code)
    ticket = await load_ticket_by_raw(db, ticket_raw)
    if ticket.purpose != "login":
        raise account_error(400, "WECHAT_TICKET_INVALID")
    assert_usable(ticket, allow=("scanned", "unbound"))
    if ticket.status == "unbound" or not ticket.user_id:
        raise account_error(401, "WECHAT_NOT_BOUND")
    if ticket.openid_hash != openid_digest(app_id_of(config), openid):
        raise account_error(400, "WECHAT_TICKET_INVALID")
    identity = await get_identity_by_openid(db, app_id_of(config), openid)
    if identity is None or identity.user_id != ticket.user_id:
        raise account_error(401, "WECHAT_NOT_BOUND")
    user = await get_user_by_id(db, ticket.user_id)
    if user is None:
        raise account_error(401, "WECHAT_NOT_BOUND")
    if not user.is_active:
        raise account_error(403, "USER_DISABLED")
    if user.approval_status != "approved":
        raise account_error(403, "ACCOUNT_PENDING")
    if not config.wechat_satisfies_mfa:
        from account_kit.two_factor.service import is_enabled

        if config.two_factor_enabled and await is_enabled(db, user.id):
            raise account_error(401, "MFA_REQUIRED", extra={"wechat_confirm": True})
    use_force = bool(force or ticket.force)
    try:
        user, body = await complete_login_tokens(
            db,
            config,
            user,
            force=use_force,
            device_name=ticket.device_name or "",
            ip=request_ip(config, request),
        )
    except Exception:
        await db.refresh(ticket)
        raise
    ticket = await load_ticket_by_raw(db, ticket_raw, touch_expiry=False)
    ticket.status = "confirmed"
    ticket.user_id = user.id
    ticket.token_hash = access_token_digest(body.get("access_token") or "")
    ticket.payload_cipher = encrypt_payload(
        config,
        {k: v for k, v in body.items() if k in ("access_token", "token_type", "refresh_token", "refresh_expires_in")},
    )
    await db.commit()
    await audit(
        db,
        config,
        audit_mod.LOGIN_WECHAT,
        user_id=user.id,
        request=request,
        device_name=ticket.device_name,
        meta={"purpose": "login"},
    )
    return {"status": "ok", "purpose": "login"}


async def confirm_bind(db: AsyncSession, config: AccountKitConfig, request, *, ticket_raw: str, js_code: str) -> dict:
    require_session_configured(config)
    await run_before_action(config, request, "wechat_confirm", {"purpose": "bind"})
    await wechat_ip_limit(db, config, request)
    openid, unionid = await exchange_js_code(config, js_code)
    ticket = await load_ticket_by_raw(db, ticket_raw)
    if ticket.purpose != "bind" or not ticket.user_id:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    assert_usable(ticket, allow=("pending", "scanned"))
    user = await get_user_by_id(db, ticket.user_id)
    if user is None:
        raise account_error(400, "WECHAT_TICKET_INVALID")
    await bind_identity(db, config, user, openid, unionid)
    ticket.status = "confirmed"
    ticket.openid_hash = openid_digest(app_id_of(config), openid)
    ticket.payload_cipher = None
    await db.commit()
    await audit(
        db,
        config,
        audit_mod.WECHAT_BOUND,
        user_id=user.id,
        request=request,
        meta={"purpose": "bind"},
    )
    return {"status": "ok", "purpose": "bind"}


async def bind_identity(db: AsyncSession, config: AccountKitConfig, user: User, openid: str, unionid: Optional[str]) -> WechatIdentity:
    app_id = app_id_of(config)
    existing = await get_identity_by_openid(db, app_id, openid)
    if existing is not None and existing.user_id != user.id:
        raise account_error(409, "WECHAT_ALREADY_BOUND")
    mine = await get_identity_by_user(db, user.id, app_id)
    if mine is not None and mine.openid != openid:
        raise account_error(409, "WECHAT_BIND_EXISTS")
    if mine is not None:
        mine.unionid = unionid or mine.unionid
        mine.updated_at = _now()
        await db.flush()
        return mine
    row = WechatIdentity(
        user_id=user.id,
        app_id=app_id,
        openid=openid,
        unionid=unionid,
        bound_at=_now(),
    )
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise account_error(409, "WECHAT_ALREADY_BOUND") from exc
    return row


async def consume_without_tokens(db: AsyncSession, ticket: WechatLoginTicket) -> None:
    ticket.status = "consumed"
    ticket.consumed_at = _now()
    ticket.payload_cipher = None
    ticket.mfa_challenge_hash = None
    await db.commit()


async def bind_existing(
    db: AsyncSession,
    config: AccountKitConfig,
    request,
    *,
    bind_ticket: str,
    username: str,
    password: str,
    force: bool = False,
    device_name: str = "",
    code: str = "",
    recovery_code: str = "",
    email_code: str = "",
    captcha_id: str = "",
    captcha_code: str = "",
) -> dict:
    from account_kit import captcha
    from account_kit.lockout import clear_lockout, enforce_not_locked, record_lockout_failure
    from account_kit.two_factor.challenges import challenge_token_hash
    from account_kit.two_factor.service import is_enabled, mfa_required, verify_second_factor, PURPOSE_LOGIN_2FA

    await run_before_action(config, request, "wechat_bind", {"username": username})
    await wechat_ip_limit(db, config, request)
    ip = request_ip(config, request)
    name = (username or "").strip()
    window = int(config.login_rate_window_seconds or 60) or 60
    if ip:
        await enforce_limit(db, config, f"login:ip:{ip}", config.login_rate_limit_ip, window)
    if name:
        await enforce_limit(db, config, f"login:user:{name.lower()}", config.login_rate_limit_user, window)
    ticket = await load_ticket_by_raw(db, bind_ticket)
    if ticket.purpose != "login":
        raise account_error(400, "WECHAT_TICKET_INVALID")
    assert_usable(ticket, allow=("unbound",))
    openid, unionid = _load_openid(config, ticket)
    candidate = await get_user_by_username(db, name) if name else None
    if candidate is not None and candidate.is_admin and config.admin_login_rate_limit_user:
        await enforce_limit(
            db, config, f"login:admin_user:{name.lower()}", config.admin_login_rate_limit_user, window
        )
    await enforce_not_locked(db, config, candidate, name)
    use_captcha = captcha.captcha_enabled(config)
    admin_always_captcha = bool(
        use_captcha and config.admin_login_captcha_always and candidate is not None and candidate.is_admin
    )
    if use_captcha:
        await captcha.enforce_login_captcha(
            db, config, ip, name, captcha_id, captcha_code, force=admin_always_captcha
        )
    from account_kit.service import _DUMMY_PASSWORD_HASH

    hashed = candidate.hashed_password if candidate is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, hashed)
    if not candidate or not password_ok:
        locked = await record_lockout_failure(db, config, candidate, name)
        if locked is not None:
            if use_captcha:
                await captcha.record_failure(db, config, ip, name)
            raise locked
        if use_captcha:
            raise await captcha.invalid_credentials(db, config, ip, name, {"WWW-Authenticate": "Bearer"})
        raise account_error(401, "INVALID_CREDENTIALS", headers={"WWW-Authenticate": "Bearer"})
    user = candidate
    if not user.is_active:
        if use_captcha:
            await captcha.clear_failures(db, config, ip, name)
        raise account_error(403, "USER_DISABLED")
    if user.approval_status != "approved":
        if use_captcha:
            await captcha.clear_failures(db, config, ip, name)
        raise account_error(403, "ACCOUNT_PENDING")
    if use_captcha:
        await captcha.clear_failures(db, config, ip, name)
    await clear_lockout(db, config, user, name)

    ticket.force = bool(force or ticket.force)
    ticket.device_name = sanitize_device_name(device_name or ticket.device_name)
    ticket.user_id = user.id
    await db.commit()
    await db.refresh(ticket)

    needs_mfa = bool(config.two_factor_enabled and await is_enabled(db, user.id))
    factor_given = bool((code or "").strip() or (recovery_code or "").strip() or (email_code or "").strip())
    if needs_mfa and not factor_given:
        exc = await mfa_required(db, user, ticket.device_name or "", config)
        extra = dict(exc.kit_extra)
        extra["bind_ticket"] = bind_ticket.strip()
        ticket.mfa_challenge_hash = challenge_token_hash(str(extra.get("challenge_token") or ""))
        await db.commit()
        raise account_error(401, "MFA_REQUIRED", extra=extra)
    if needs_mfa and factor_given:
        await verify_second_factor(
            db,
            config,
            user,
            code=code or "",
            recovery_code=recovery_code or "",
            email_code=email_code or "",
            email_purpose=PURPOSE_LOGIN_2FA if (email_code or "").strip() else "",
        )

    await bind_identity(db, config, user, openid, unionid)
    user, body = await complete_login_tokens(
        db,
        config,
        user,
        force=bool(force or ticket.force),
        device_name=ticket.device_name or "",
        ip=ip,
    )
    ticket = await load_ticket_by_raw(db, bind_ticket, touch_expiry=False)
    ticket.user_id = user.id
    ticket.token_hash = access_token_digest(body.get("access_token") or "")
    await consume_without_tokens(db, ticket)
    await audit(db, config, audit_mod.WECHAT_BOUND, user_id=user.id, request=request, meta={"via": "bind-existing"})
    await audit(
        db,
        config,
        audit_mod.LOGIN_WECHAT,
        user_id=user.id,
        request=request,
        device_name=ticket.device_name,
        meta={"via": "bind-existing"},
    )
    return body


async def complete_pending_wechat_bind(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    challenge_token: str,
    *,
    force: bool,
    device_name: str,
    ip: str,
    request=None,
) -> Optional[dict]:
    """If this 2FA challenge was issued by bind-existing, bind and issue tokens."""
    from account_kit.two_factor.challenges import challenge_token_hash

    digest = challenge_token_hash(challenge_token)
    result = await db.execute(
        select(WechatLoginTicket).where(WechatLoginTicket.mfa_challenge_hash == digest)
    )
    ticket = result.scalars().first()
    if ticket is None:
        return None
    ticket = await refresh_ticket_status(db, ticket)
    if ticket.purpose != "login" or ticket.status != "unbound":
        return None
    openid, unionid = _load_openid(config, ticket)
    await bind_identity(db, config, user, openid, unionid)
    user, body = await complete_login_tokens(
        db,
        config,
        user,
        force=bool(force or ticket.force),
        device_name=device_name or ticket.device_name or "",
        ip=ip,
    )
    ticket = await db.get(WechatLoginTicket, ticket.id)
    if ticket is not None:
        ticket.user_id = user.id
        ticket.token_hash = access_token_digest(body.get("access_token") or "")
        ticket.status = "consumed"
        ticket.consumed_at = _now()
        ticket.payload_cipher = None
        ticket.mfa_challenge_hash = None
        await db.commit()
    await audit(db, config, audit_mod.WECHAT_BOUND, user_id=user.id, request=request, meta={"via": "login-2fa"})
    await audit(
        db,
        config,
        audit_mod.LOGIN_WECHAT,
        user_id=user.id,
        request=request,
        device_name=device_name,
        meta={"via": "login-2fa"},
    )
    return body


async def register_with_wechat(
    db: AsyncSession,
    config: AccountKitConfig,
    request,
    payload: RegisterRequest,
    bind_ticket: str,
) -> dict:
    if not config.wechat_allow_register:
        raise account_error(403, "WECHAT_REGISTER_DISABLED")
    await run_before_action(config, request, "wechat_register", {"email": payload.email})
    await wechat_ip_limit(db, config, request)
    ip = request_ip(config, request)
    if ip:
        await enforce_limit(
            db, config, f"register:ip:{ip}", config.register_rate_limit_ip, config.register_rate_window_seconds
        )
    if config.before_register is not None:
        await config.before_register(request)
    ticket = await load_ticket_by_raw(db, bind_ticket)
    if ticket.purpose != "login":
        raise account_error(400, "WECHAT_TICKET_INVALID")
    assert_usable(ticket, allow=("unbound",))
    openid, unionid = _load_openid(config, ticket)
    taken = await get_identity_by_openid(db, app_id_of(config), openid)
    if taken is not None:
        raise account_error(409, "WECHAT_ALREADY_BOUND")
    user = await register_user(db, config, payload)
    await bind_identity(db, config, user, openid, unionid)
    ticket = await load_ticket_by_raw(db, bind_ticket, touch_expiry=False)
    ticket.user_id = user.id
    await consume_without_tokens(db, ticket)
    await audit(db, config, audit_mod.WECHAT_REGISTER, user_id=user.id, request=request)
    from account_kit.service import to_response

    if config.require_approval and user.approval_status != "approved":
        return (await to_response(db, user)).model_dump(mode="json")
    user, body = await complete_login_tokens(
        db, config, user, force=bool(ticket.force), device_name=ticket.device_name or "", ip=ip
    )
    await audit(
        db,
        config,
        audit_mod.LOGIN_WECHAT,
        user_id=user.id,
        request=request,
        device_name=ticket.device_name,
        meta={"via": "register"},
    )
    return body


async def bind_status(db: AsyncSession, config: AccountKitConfig, user: User) -> dict:
    row = await get_identity_by_user(db, user.id, app_id_of(config))
    if row is None:
        return {"bound": False, "openid_masked": None, "bound_at": None}
    return {
        "bound": True,
        "openid_masked": mask_openid(row.openid),
        "bound_at": row.bound_at.isoformat() if row.bound_at else None,
    }


async def unbind(
    db: AsyncSession,
    config: AccountKitConfig,
    request,
    user: User,
    *,
    password: str,
    code: str = "",
    recovery_code: str = "",
    email_code: str = "",
) -> dict:
    from account_kit.two_factor.service import is_enabled, verify_second_factor, PURPOSE_DISABLE_2FA

    await run_before_action(config, request, "wechat_unbind", {"user": user})
    if not verify_password(password or "", user.hashed_password):
        raise account_error(400, "PASSWORD_INCORRECT")
    if config.two_factor_enabled and await is_enabled(db, user.id):
        if not (code or "").strip() and not (recovery_code or "").strip() and not (email_code or "").strip():
            raise account_error(400, "MFA_CODE_REQUIRED", as_dict=True)
        await verify_second_factor(
            db,
            config,
            user,
            code=code or "",
            recovery_code=recovery_code or "",
            email_code=email_code or "",
            email_purpose=PURPOSE_DISABLE_2FA if (email_code or "").strip() else "",
        )
    row = await get_identity_by_user(db, user.id, app_id_of(config))
    if row is not None:
        digest = openid_digest(app_id_of(config), row.openid)
        await db.delete(row)
        await db.execute(
            update(WechatLoginTicket)
            .where(
                WechatLoginTicket.status.in_(OPEN_STATUSES),
                or_(WechatLoginTicket.user_id == user.id, WechatLoginTicket.openid_hash == digest),
            )
            .values(status="cancelled", payload_cipher=None, mfa_challenge_hash=None)
        )
    else:
        await invalidate_user_tickets(db, user.id)
    await db.commit()
    await audit(db, config, audit_mod.WECHAT_UNBOUND, user_id=user.id, request=request)
    return {"bound": False}


async def invalidate_user_tickets(db: AsyncSession, user_id) -> None:
    """Cancel unconsumed tickets for this user. Does not remove the identity."""
    if user_id is None:
        return
    await db.execute(
        update(WechatLoginTicket)
        .where(WechatLoginTicket.user_id == user_id, WechatLoginTicket.status.in_(OPEN_STATUSES))
        .values(status="cancelled", payload_cipher=None, mfa_challenge_hash=None)
    )


async def delete_user_identities(db: AsyncSession, user_id) -> None:
    if user_id is None:
        return
    await db.execute(delete(WechatIdentity).where(WechatIdentity.user_id == user_id))
    await invalidate_user_tickets(db, user_id)
