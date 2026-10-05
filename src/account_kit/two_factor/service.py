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
from account_kit.models import TwoFactorRecoveryCode, TrustedDevice, User, UserTwoFactor
from account_kit.two_factor.challenges import challenge_store
from account_kit.two_factor.totp import decrypt_secret, encrypt_secret, generate_secret, match_step, provisioning_uri

RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


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


async def verify_second_factor(db: AsyncSession, config: AccountKitConfig, user: User, *, code: str = "", recovery_code: str = "") -> str:
    row = await get_row(db, user.id)
    if row is None or not row.enabled:
        raise HTTPException(status_code=400, detail="未开启两步验证")
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
    raise HTTPException(status_code=400, detail="缺少验证码")


async def disable(db: AsyncSession, config: AccountKitConfig, user: User, password: str, code: str = "", recovery_code: str = "") -> None:
    from account_kit.security import verify_password

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    await verify_second_factor(db, config, user, code=code, recovery_code=recovery_code)
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
    challenge_store.discard_user(user.id)
    await db.commit()


async def admin_reset(db: AsyncSession, user_id) -> None:
    row = await get_row(db, user_id)
    if row:
        row.enabled = False
        row.secret = None
        row.pending_secret = None
        row.last_step = None
    result = await db.execute(select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user_id))
    for item in result.scalars().all():
        await db.delete(item)
    await revoke_trusted(db, user_id)
    challenge_store.discard_user(user_id)
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
        "email_available": False,
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


def mfa_required(user: User, device_name: str = "") -> HTTPException:
    token = challenge_store.create(user.id, user.hashed_password, device_name=device_name)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "MFA_REQUIRED",
            "message": "该账号已开启两步验证，请升级客户端",
            "challenge_token": token,
            "methods": ["totp", "recovery"],
            "expires_in": 300,
        },
    )


