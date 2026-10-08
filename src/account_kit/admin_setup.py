"""Host-facing bootstrap: create or reuse the single admin account."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig, get_config
from account_kit.i18n import AccountError, account_error, error_code_of, t
from account_kit.models import User, UserTierAssignment
from account_kit.otp import normalize_email
from account_kit.security import hash_password
from account_kit.seed import default_role, default_tier
from account_kit.service import assert_password, assert_username, get_user_by_email, get_user_by_username


class AdminSetupError(Exception):
    """Raised by :func:`ensure_admin` when the single-admin invariant would break."""

    def __init__(self, code: str, message: str = "", *, message_key: Optional[str] = None):
        self.code = code
        self.message_key = message_key or code
        self.message = message or t(self.message_key)
        super().__init__(self.message)

    def http(self) -> AccountError:
        return account_error(400, self.code, as_dict=True, message_key=self.message_key)


def _resolve_config(config: Optional[AccountKitConfig]) -> AccountKitConfig:
    if config is not None:
        return config
    try:
        return get_config()
    except RuntimeError:
        return AccountKitConfig(jwt_secret="ensure-admin")


def _password_or_raise(config: AccountKitConfig, password: str) -> None:
    try:
        assert_password(config, password, admin=True)
    except Exception as exc:
        code = error_code_of(exc) or "PASSWORD_TOO_SHORT"
        raise AdminSetupError(code) from exc


async def ensure_admin(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    *,
    reset_password: bool = False,
    config: Optional[AccountKitConfig] = None,
) -> User:
    """Create the single admin, or no-op when that username is already admin.

    Does not reset the password unless ``reset_password=True``. Refuses if a
    different admin exists, or if ``username`` / ``email`` belongs to a
    non-admin (no takeover).
    """
    cfg = _resolve_config(config)
    name = assert_username(cfg, username)
    email_n = normalize_email(email)

    admins = list((await db.execute(select(User).where(User.is_admin.is_(True)))).scalars().all())
    if len(admins) > 1:
        raise AdminSetupError("ADMIN_ALREADY_EXISTS", message_key="ADMIN_ALREADY_EXISTS_MULTI")

    if admins:
        admin = admins[0]
        if admin.username != name:
            raise AdminSetupError("ADMIN_ALREADY_EXISTS", message_key="ADMIN_ALREADY_EXISTS_OTHER")
        if reset_password:
            _password_or_raise(cfg, password)
            admin.hashed_password = hash_password(password)
            await db.commit()
            await db.refresh(admin)
        return admin

    by_name = await get_user_by_username(db, name)
    if by_name is not None:
        raise AdminSetupError("ADMIN_USERNAME_TAKEN")
    by_email = await get_user_by_email(db, email_n)
    if by_email is not None:
        raise AdminSetupError("ADMIN_EMAIL_TAKEN")

    _password_or_raise(cfg, password)
    role = await default_role(db)
    now = datetime.now(timezone.utc)
    user = User(
        username=name,
        email=email_n,
        hashed_password=hash_password(password),
        role=role.code,
        is_admin=True,
        is_active=True,
        approval_status="approved",
        approved_at=now,
    )
    db.add(user)
    try:
        await db.flush()
        tier = await default_tier(db)
        db.add(UserTierAssignment(user_id=user.id, tier_code=tier.code))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AdminSetupError("ADMIN_ALREADY_EXISTS") from exc
    await db.refresh(user)
    return user
