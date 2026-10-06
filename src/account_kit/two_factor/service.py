from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig
from account_kit.models import TwoFactorRecoveryCode, TrustedDevice, User, UserTwoFactor, VerificationCode
from account_kit.two_factor.challenges import TTL_SECONDS, challenge_store, create_challenge, discard_user_challenges  # noqa: F401
from account_kit.two_factor.totp import decrypt_secret, encrypt_secret, generate_secret, match_step, provisioning_uri

RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
PURPOSE_LOGIN_2FA = "login_2fa"
PURPOSE_DISABLE_2FA = "disable_2fa"
EMAIL_CODE_COOLDOWN = timedelta(seconds=60)


def _err(status_code: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def email_factor_available(config: AccountKitConfig, user: User) -> bool:
    return bool(config.two_factor_email_enabled and user.email)


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    shown = name[:2] if len(name) > 2 else name[:1]
    return f"{shown}***@{domain}"


def _hash_recovery(secret: str, user_id, code: str) -> str:
    normalized = "".join(ch for ch in str(code or "").lower() if ch.isalnum())
    material = f"2fa-recovery:{user_id}:{normalized}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def _hash_device(token: str) -> str:
    return hashlib.sha256(("device:" + token).encode("utf-8")).hexdigest()


def _new_recovery_codes() -> List[str]:
    codes = []
    for _ in range(10):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


async def get_row(db: AsyncSession, user_id) -> Optional[UserTwoFactor]:
    return await db.get(UserTwoFactor, user_id)


async def is_enabled(db: AsyncSession, user_id) -> bool:
    row = await get_row(db, user_id)
    return bool(row and row.enabled)


async def start_setup(db: AsyncSession, config: AccountKitConfig, user: User) -> dict:
    secret = generate_secret()
    row = await get_row(db, user.id)
    if row is None:
        row = UserTwoFactor(user_id=user.id, enabled=False)
        db.add(row)
    row.pending_secret = encrypt_secret(secret, config.encryption_material())
    row.pending_created_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "otpauth_uri": provisioning_uri(secret, user.email, config.brand_name),
        "secret": secret,
    }


async def enable(db: AsyncSession, config: AccountKitConfig, user: User, code: str) -> List[str]:
    row = await get_row(db, user.id)
    pending = decrypt_secret(row.pending_secret, config.encryption_material()) if row else None
    if not pending:
        raise HTTPException(status_code=400, detail="请先开始设置两步验证")
    step = match_step(pending, code)
    if step is None:
        raise HTTPException(status_code=400, detail={"code": "MFA_CODE_INVALID", "message": "验证码错误"})
    row.secret = row.pending_secret
    row.pending_secret = None
    row.enabled = True
    row.enabled_at = datetime.now(timezone.utc)
    row.last_step = step
    codes = _new_recovery_codes()
    existing = await db.execute(select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id))
    for old in existing.scalars().all():
        await db.delete(old)
    for item in codes:
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=_hash_recovery(config.code_secret(), user.id, item)))
    await db.commit()
    return codes


async def verify_second_factor(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    *,
    code: str = "",
    recovery_code: str = "",
    email_code: str = "",
    email_purpose: str = "",
) -> str:
    row = await get_row(db, user.id)
    if row is None or not row.enabled:
        raise HTTPException(status_code=400, detail="未开启两步验证")
    if email_code and email_purpose and not code and not recovery_code:
        return await consume_email_factor(db, config, user, email_purpose, email_code)
    if code:
        secret = decrypt_secret(row.secret, config.encryption_material())
        step = match_step(secret, code, row.last_step)
        if step is None:
            raise HTTPException(status_code=400, detail={"code": "MFA_CODE_INVALID", "message": "验证码错误"})
        row.last_step = step
        await db.commit()
        return "totp"
    if recovery_code:
        digest = _hash_recovery(config.code_secret(), user.id, recovery_code)
        result = await db.execute(
            select(TwoFactorRecoveryCode).where(
                TwoFactorRecoveryCode.user_id == user.id,
                TwoFactorRecoveryCode.code_hash == digest,
                TwoFactorRecoveryCode.used_at.is_(None),
            )
        )
        found = result.scalars().first()
        if found is None:
            raise HTTPException(status_code=400, detail={"code": "MFA_CODE_INVALID", "message": "恢复码错误"})
        found.used_at = datetime.now(timezone.utc)
        await db.commit()
        return "recovery"
    raise _err(400, "MFA_CODE_REQUIRED", "请输入验证码")


async def consume_email_factor(db: AsyncSession, config: AccountKitConfig, user: User, purpose: str, email_code: str) -> str:
    """Single-use check of an emailed 2FA code; marks it used on success."""
    if not config.two_factor_email_enabled:
        raise _err(400, "EMAIL_UNAVAILABLE", "邮箱验证不可用")
    from account_kit.otp import CODE_LOCKED_MESSAGE, check_code

    value = (email_code or "").strip()
    if not user.email or not value:
        raise _err(400, "EMAIL_CODE_INVALID", "邮箱验证码错误或已失效")
    try:
        await check_code(db, config, user.email, purpose, value)
    except HTTPException as exc:
        if exc.detail == CODE_LOCKED_MESSAGE:
            raise _err(400, "EMAIL_CODE_LOCKED", CODE_LOCKED_MESSAGE) from exc
        raise _err(400, "EMAIL_CODE_INVALID", "邮箱验证码错误或已失效") from exc
    await db.commit()
    return "email"


async def send_email_code(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    purpose: str,
    language: str = "zh",
    background_tasks=None,
) -> dict:
    """Issue a 6-digit code (hashed at rest, 5 min TTL, 60 s cooldown) and email it."""
    from account_kit.emailer import send_code_email
    from account_kit.otp import OTP_TTL, create_code, generate_otp, normalize_email

    if not user.email:
        raise _err(400, "EMAIL_UNAVAILABLE", "账号未绑定邮箱")
    email = normalize_email(user.email)
    result = await db.execute(
        select(VerificationCode)
        .where(VerificationCode.email == email, VerificationCode.purpose == purpose)
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    last = result.scalars().first()
    if last is not None and last.created_at is not None:
        created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created < EMAIL_CODE_COOLDOWN:
            raise _err(429, "EMAIL_CODE_TOO_FREQUENT", "验证码发送频繁，请稍后再试")
    code = generate_otp()
    await create_code(db, config.code_secret(), email, purpose, code)
    from account_kit.otp import reset_attempts

    await reset_attempts(db, config, email, purpose)
    lang = language if language in ("zh", "en") else "zh"
    if config.mailer is None and background_tasks is not None:
        background_tasks.add_task(send_code_email, config, email, purpose, code, lang)
    else:
        await send_code_email(config, email, purpose, code, lang)
    return {
        "status": "success",
        "email": mask_email(email),
        "expires_in": int(OTP_TTL.total_seconds()),
        "cooldown": int(EMAIL_CODE_COOLDOWN.total_seconds()),
    }


async def disable(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    password: str,
    code: str = "",
    recovery_code: str = "",
    email_code: str = "",
) -> None:
    from account_kit.security import verify_password

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    await verify_second_factor(
        db, config, user, code=code, recovery_code=recovery_code, email_code=email_code, email_purpose=PURPOSE_DISABLE_2FA
    )
    row = await get_row(db, user.id)
    if row:
        row.enabled = False
        row.secret = None
        row.pending_secret = None
        row.last_step = None
    result = await db.execute(select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id))
    for item in result.scalars().all():
        await db.delete(item)
    await revoke_trusted(db, user.id)
    await discard_user_challenges(db, config, user.id)
    from account_kit.tokens import revoke_user_tokens

    await revoke_user_tokens(db, user.id, "two_factor_disabled")
    await db.commit()


async def wipe_two_factor(db: AsyncSession, user_id) -> None:
    """Turn 2FA off and drop recovery codes (caller commits)."""
    row = await get_row(db, user_id)
    if row:
        row.enabled = False
        row.secret = None
        row.pending_secret = None
        row.last_step = None
    result = await db.execute(select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user_id))
    for item in result.scalars().all():
        await db.delete(item)


async def admin_reset(db: AsyncSession, user_id, config: Optional[AccountKitConfig] = None) -> None:
    from account_kit.tokens import revoke_user_tokens

    if config is None:
        from account_kit.config import _config as current

        config = current
    await wipe_two_factor(db, user_id)
    await revoke_trusted(db, user_id)
    await discard_user_challenges(db, config, user_id)
    await revoke_user_tokens(db, user_id, "admin")
    await db.commit()


async def issue_trusted_device(db: AsyncSession, config: AccountKitConfig, user_id, device_name: str) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=config.trusted_device_days)
    db.add(
        TrustedDevice(
            user_id=user_id,
            token_hash=_hash_device(raw),
            device_name=device_name or None,
            expires_at=expires,
        )
    )
    await db.commit()
    return raw, expires


async def trusted_device_ok(db: AsyncSession, user_id, token: Optional[str]) -> bool:
    if not token:
        return False
    result = await db.execute(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.token_hash == _hash_device(token),
            TrustedDevice.revoked_at.is_(None),
            TrustedDevice.expires_at > datetime.now(timezone.utc),
        )
    )
    row = result.scalars().first()
    if row is None:
        return False
    row.last_used_at = datetime.now(timezone.utc)
    return True


def _require_password(user: User, password: str) -> None:
    from account_kit.security import verify_password

    if not verify_password(password or "", user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码错误")


async def recovery_codes_remaining(db: AsyncSession, user_id) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(TwoFactorRecoveryCode)
        .where(TwoFactorRecoveryCode.user_id == user_id, TwoFactorRecoveryCode.used_at.is_(None))
    )
    return int(result.scalar_one())


async def list_trusted_devices(db: AsyncSession, user_id) -> List[TrustedDevice]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TrustedDevice)
        .where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.revoked_at.is_(None),
            TrustedDevice.expires_at > now,
        )
        .order_by(TrustedDevice.created_at.desc())
    )
    return list(result.scalars().all())


def device_public(dev: TrustedDevice) -> dict:
    return {
        "id": str(dev.id),
        "device_name": dev.device_name or "未知设备",
        "created_at": dev.created_at.isoformat() if dev.created_at else None,
        "last_used_at": dev.last_used_at.isoformat() if dev.last_used_at else None,
        "expires_at": dev.expires_at.isoformat() if dev.expires_at else None,
    }


async def status_payload(db: AsyncSession, config: AccountKitConfig, user: User) -> dict:
    row = await get_row(db, user.id)
    enabled = bool(row and row.enabled and row.secret)
    devices = await list_trusted_devices(db, user.id) if enabled else []
    return {
        "enabled": enabled,
        "enabled_at": row.enabled_at.isoformat() if enabled and row.enabled_at else None,
        "recovery_codes_remaining": await recovery_codes_remaining(db, user.id) if enabled else 0,
        "trusted_devices": len(devices),
        "email_available": email_factor_available(config, user),
        "trusted_device_days": int(config.trusted_device_days),
    }


async def regenerate_recovery_codes(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    password: str,
    code: str = "",
    recovery_code: str = "",
) -> List[str]:
    _require_password(user, password)
    if not await is_enabled(db, user.id):
        raise HTTPException(status_code=400, detail="未开启两步验证")
    await verify_second_factor(db, config, user, code=code, recovery_code=recovery_code)
    codes = _new_recovery_codes()
    existing = await db.execute(select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id))
    for old in existing.scalars().all():
        await db.delete(old)
    for item in codes:
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=_hash_recovery(config.code_secret(), user.id, item)))
    await db.commit()
    return codes


async def revoke_trusted_device(db: AsyncSession, user_id, device_id: str) -> bool:
    try:
        parsed = uuid.UUID(str(device_id))
    except ValueError:
        return False
    row = await db.get(TrustedDevice, parsed)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def revoke_all_trusted(db: AsyncSession, user_id) -> int:
    result = await db.execute(
        select(TrustedDevice).where(TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None))
    )
    rows = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
    await db.commit()
    return len(rows)


async def revoke_trusted(db: AsyncSession, user_id) -> None:
    result = await db.execute(
        select(TrustedDevice).where(TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None))
    )
    now = datetime.now(timezone.utc)
    for row in result.scalars().all():
        row.revoked_at = now


async def mfa_required(
    db: AsyncSession, user: User, device_name: str = "", config: Optional[AccountKitConfig] = None
) -> HTTPException:
    """401 (non-200 on purpose: old clients show ``message`` instead of treating
    the response as a successful login)."""
    ttl = config.challenge_ttl() if config is not None else TTL_SECONDS
    token = await create_challenge(db, config, user.id, user.hashed_password, device_name, ttl)
    email_ok = bool(config is not None and email_factor_available(config, user))
    detail = {
        "code": "MFA_REQUIRED",
        "message": "该账号已开启两步验证，请升级客户端",
        "challenge_token": token,
        "methods": ["totp", "recovery"] + (["email"] if email_ok else []),
        "email_available": email_ok,
        "expires_in": ttl,
    }
    if config is not None:
        detail["trusted_device_days"] = int(config.trusted_device_days)
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
