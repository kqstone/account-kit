"""Per-account login lockout (fixed window, shared with rate-limit counters)."""

from __future__ import annotations

from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig
from account_kit.models import User
from account_kit.state import counter_clear, counter_get, counter_hit, counter_ttl


def lockout_settings(config: AccountKitConfig, user: Optional[User]) -> Tuple[int, int]:
    if user is not None and user.is_admin:
        return int(config.admin_login_lockout_attempts or 0), max(1, int(config.admin_login_lockout_seconds or 900))
    return int(config.login_lockout_attempts or 0), max(1, int(config.login_lockout_seconds or 900))


def lockout_key(user: Optional[User], username: str) -> str:
    if user is not None:
        return f"login_lock:id:{user.id}"
    return f"login_lock:name:{(username or '').strip().lower()}"


def account_locked(retry_after: int) -> HTTPException:
    ttl = max(1, int(retry_after or 1))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "ACCOUNT_LOCKED",
            "message": "登录失败次数过多，请稍后再试",
            "retry_after": ttl,
        },
        headers={"Retry-After": str(ttl)},
    )


async def enforce_not_locked(db: AsyncSession, config: AccountKitConfig, user: Optional[User], username: str) -> None:
    attempts, _seconds = lockout_settings(config, user)
    if attempts <= 0:
        return
    key = lockout_key(user, username)
    count = await counter_get(db, config, key)
    if count >= attempts:
        raise account_locked(await counter_ttl(db, config, key))


async def record_lockout_failure(
    db: AsyncSession, config: AccountKitConfig, user: Optional[User], username: str
) -> Optional[HTTPException]:
    """Count one failed password. Returns ACCOUNT_LOCKED when the threshold is reached."""
    attempts, seconds = lockout_settings(config, user)
    if attempts <= 0:
        return None
    key = lockout_key(user, username)
    count, ttl = await counter_hit(db, config, key, seconds)
    if count >= attempts:
        return account_locked(ttl)
    return None


async def clear_lockout(db: AsyncSession, config: AccountKitConfig, user: Optional[User], username: str) -> None:
    attempts, _seconds = lockout_settings(config, user)
    if attempts <= 0:
        return
    await counter_clear(db, config, lockout_key(user, username))
