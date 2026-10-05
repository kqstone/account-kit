from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.models import VerificationCode

OTP_PURPOSES = {"register", "reset_password", "change_password", "login_2fa", "disable_2fa"}
OTP_TTL = timedelta(minutes=5)
OTP_RESEND_WINDOW = timedelta(minutes=5)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(secret: str, email: str, purpose: str, code: str) -> str:
    material = f"{secret}:{normalize_email(email)}:{(purpose or '')}:{code or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def find_valid_code(db: AsyncSession, secret: str, email: str, purpose: str, code: str):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == normalize_email(email),
            VerificationCode.purpose == purpose,
            VerificationCode.used.is_(False),
            VerificationCode.expires_at > now,
        )
    )
    expected = hash_otp(secret, email, purpose, code)
    for row in result.scalars().all():
        stored = row.code or ""
        if hmac.compare_digest(stored, expected):
            return row
    return None


async def consume_code(db: AsyncSession, secret: str, email: str, purpose: str, code: Optional[str]):
    if not code:
        raise HTTPException(status_code=400, detail="验证码错误或已失效")
    row = await find_valid_code(db, secret, email, purpose, code)
    if not row:
        raise HTTPException(status_code=400, detail="验证码错误或已失效")
    row.used = True
    return row


async def assert_resend_allowed(db: AsyncSession, email: str, purpose: str) -> None:
    result = await db.execute(
        select(VerificationCode)
        .where(
            VerificationCode.email == normalize_email(email),
            VerificationCode.purpose == purpose,
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    last = result.scalars().first()
    if not last:
        return
    created = _aware(last.created_at)
    if created and datetime.now(timezone.utc) - created < OTP_RESEND_WINDOW:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="验证码发送频繁，请稍后再试")


async def create_code(db: AsyncSession, secret: str, email: str, purpose: str, code: str) -> VerificationCode:
    now = datetime.now(timezone.utc)
    row = VerificationCode(
        email=normalize_email(email),
        code=hash_otp(secret, email, purpose, code),
        purpose=purpose,
        created_at=now,
        expires_at=now + OTP_TTL,
        used=False,
    )
    db.add(row)
    await db.commit()
    return row
