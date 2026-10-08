from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.i18n import account_error
from account_kit.models import VerificationCode

OTP_PURPOSES = {
    "register",
    "reset_password",
    "change_password",
    "login_2fa",
    "disable_2fa",
    "change_email",
    "delete_account",
}
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
        raise account_error(400, "CODE_INVALID")
    row = await find_valid_code(db, secret, email, purpose, code)
    if not row:
        raise account_error(400, "CODE_INVALID")
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
        raise account_error(429, "EMAIL_CODE_TOO_FREQUENT")


async def create_code(
    db: AsyncSession, secret: str, email: str, purpose: str, code: str, *, bind=None
) -> VerificationCode:
    now = datetime.now(timezone.utc)
    row = VerificationCode(
        email=normalize_email(email),
        code=hash_otp(bound_secret(secret, bind), email, purpose, code),
        purpose=purpose,
        created_at=now,
        expires_at=now + OTP_TTL,
        used=False,
    )
    db.add(row)
    await db.commit()
    return row


# --- 0.2.2: wrong-attempt cap and send limits ---------------------------------


def bound_secret(secret: str, bind=None) -> str:
    """Codes bound to a user (e.g. change_email sent to an address the user does not
    own yet) mix the user id into the hash so nobody else can redeem them."""
    return f"{secret}:{bind}" if bind else secret


def _fail_key(email: str, purpose: str) -> str:
    return f"otp_fail:{purpose}:{normalize_email(email)}"


async def invalidate_codes(db: AsyncSession, email: str, purpose: str) -> None:
    from account_kit.state import run_independent

    stmt = (
        update(VerificationCode)
        .where(
            VerificationCode.email == normalize_email(email),
            VerificationCode.purpose == purpose,
            VerificationCode.used.is_(False),
        )
        .values(used=True)
    )

    async def work(conn):
        await conn.execute(stmt)

    await run_independent(db, work)


async def check_code(
    db: AsyncSession,
    config,
    email: str,
    purpose: str,
    code: Optional[str],
    *,
    consume: bool = True,
    bind=None,
    missing_detail=None,
    missing_code: Optional[str] = None,
):
    """Validate an emailed code. Each wrong code counts against email+purpose;
    after ``config.verify_code_max_attempts`` wrong codes every outstanding code for
    that email+purpose is invalidated. Returns the row (marked used if ``consume``)."""
    from account_kit.state import counter_clear, counter_hit

    value = (code or "").strip()
    if not value:
        if missing_code:
            extra = {"email_code_required": True}
            if isinstance(missing_detail, dict):
                extra.update({k: v for k, v in missing_detail.items() if k not in ("code", "message")})
            raise account_error(400, missing_code, extra=extra, as_dict=True)
        if isinstance(missing_detail, dict) and missing_detail.get("code"):
            extra = {k: v for k, v in missing_detail.items() if k not in ("code", "message")}
            raise account_error(400, str(missing_detail["code"]), extra=extra, as_dict=True)
        raise account_error(400, "CODE_INVALID")
    secret = bound_secret(config.code_secret(), bind)
    row = await find_valid_code(db, secret, email, purpose, value)
    limit = int(config.verify_code_max_attempts or 0)
    if row is None:
        if limit > 0:
            window = int(OTP_TTL.total_seconds()) + 60
            count, _ttl = await counter_hit(db, config, _fail_key(email, purpose), window)
            if count >= limit:
                await invalidate_codes(db, email, purpose)
                await counter_clear(db, config, _fail_key(email, purpose))
                from account_kit.audit import CODE_LOCKED, audit

                await audit(db, config, CODE_LOCKED, meta={"email": normalize_email(email), "purpose": purpose})
                raise account_error(400, "CODE_LOCKED")
        raise account_error(400, "CODE_INVALID")
    if limit > 0:
        await counter_clear(db, config, _fail_key(email, purpose))
    if consume:
        row.used = True
    return row


async def reset_attempts(db: AsyncSession, config, email: str, purpose: str) -> None:
    from account_kit.state import counter_clear

    if int(config.verify_code_max_attempts or 0) > 0:
        await counter_clear(db, config, _fail_key(email, purpose))


async def run_before_action(config, request, action: str, info: Optional[dict] = None) -> None:
    if config.before_action is not None and request is not None:
        await config.before_action(request, action, info or {})


async def guard_send(db: AsyncSession, config, request, email: str, purpose: str) -> None:
    """Host hooks plus per-IP / per-email send limits for every emailed code."""
    from account_kit.audit import request_ip
    from account_kit.state import enforce_limit

    email = normalize_email(email)
    if config.before_send_code is not None and request is not None:
        await config.before_send_code(request, email, purpose)
    await run_before_action(config, request, "send_code", {"email": email, "purpose": purpose})
    window = int(config.send_code_rate_window_seconds or 3600)
    ip = request_ip(config, request)
    if ip:
        await enforce_limit(
            db, config, f"send_code:ip:{ip}", config.send_code_rate_limit_ip, window, message_key="SEND_CODE_RATE_LIMITED"
        )
    await enforce_limit(
        db, config, f"send_code:email:{email}", config.send_code_rate_limit_email, window, message_key="SEND_CODE_RATE_LIMITED"
    )
