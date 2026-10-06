"""Opt-in refresh tokens (``refresh_token_enabled=True``).

* Opaque random token, stored as SHA-256 in ``auth.refresh_tokens``.
* Every POST /refresh rotates: the old row is revoked (``rotated``) and a new one
  in the same ``family_id`` is issued.
* Presenting a rotated token again is treated as theft: the whole family is
  revoked (``reuse_detected``), the single-device session it belongs to is
  cleared, and an audit row is written.
* ``single_device``: a refresh token is bound to the session id it was issued
  with; once another login replaces the session it stops working.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig
from account_kit.models import RefreshToken, User


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(("refresh:" + (raw or "")).encode("utf-8")).hexdigest()


def _ttl(config: AccountKitConfig) -> timedelta:
    return timedelta(days=max(1, int(config.refresh_token_expire_days or 30)))


def refresh_expires_in(config: AccountKitConfig) -> int:
    return int(_ttl(config).total_seconds())


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def refresh_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def issue_refresh_token(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    *,
    session_id: Optional[str] = None,
    device_name: str = "",
    ip: str = "",
    family_id: Optional[uuid.UUID] = None,
) -> Tuple[str, RefreshToken]:
    """Add a new refresh token to the session (caller commits)."""
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh(raw),
        session_id=session_id,
        device_name=(device_name or "")[:128] or None,
        ip=(ip or "")[:64] or None,
        expires_at=datetime.now(timezone.utc) + _ttl(config),
    )
    db.add(row)
    return raw, row


async def revoke_user_tokens(db: AsyncSession, user_id, reason: str, *, except_family=None) -> None:
    """Revoke every live refresh token of a user (caller commits)."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc), revoked_reason=reason[:32])
    )
    if except_family is not None:
        stmt = stmt.where(RefreshToken.family_id != except_family)
    await db.execute(stmt)


async def revoke_family(db: AsyncSession, family_id, reason: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc), revoked_reason=reason[:32])
    )


async def find_token(db: AsyncSession, raw: Optional[str], *, lock: bool = False) -> Optional[RefreshToken]:
    if not raw or len(raw) > 512:
        return None
    stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(raw.strip()))
    if lock:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return result.scalars().first()


async def revoke_token_family(db: AsyncSession, raw: Optional[str], reason: str, *, user_id=None) -> bool:
    """Logout helper: revoke the family of ``raw`` (only if it belongs to ``user_id`` when given)."""
    row = await find_token(db, raw)
    if row is None or (user_id is not None and row.user_id != user_id):
        return False
    await revoke_family(db, row.family_id, reason)
    return True
