"""Password + captcha + lockout + approval + optional admin ban + 2FA for bind-existing.

Does not write identity tables. ``MFA_REQUIRED`` leaves the bind ticket unconsumed;
the caller attaches ``bind_ticket`` on the error extra and (for SSO) calls
``attach_mfa_challenge``. SSO 2FA retry is another POST to the host bind-existing
route, not kit ``POST /login/2fa``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import captcha
from account_kit.approval import assert_login_allowed
from account_kit.audit import request_ip
from account_kit.config import AccountKitConfig
from account_kit.i18n import AccountError, account_error
from account_kit.lockout import clear_lockout, enforce_not_locked, record_lockout_failure
from account_kit.models import User
from account_kit.security import verify_password
from account_kit.service import _DUMMY_PASSWORD_HASH, get_user_by_email, get_user_by_username
from account_kit.state import enforce_limit
from account_kit.two_factor.service import PURPOSE_LOGIN_2FA, is_enabled, mfa_required, verify_second_factor


async def lookup_bind_user(db: AsyncSession, username: str) -> Optional[User]:
    """Username exact match, or email (case-insensitive) when ``username`` contains ``@``."""
    name = (username or "").strip()
    if not name:
        return None
    if "@" in name:
        return await get_user_by_email(db, name)
    return await get_user_by_username(db, name)


async def verify_bind_target(
    db: AsyncSession,
    config: AccountKitConfig,
    request,
    *,
    username: str,
    password: str,
    code: str = "",
    recovery_code: str = "",
    email_code: str = "",
    captcha_id: str = "",
    captcha_code: str = "",
    forbid_admin: bool = True,
    login_purpose: str = "sso_bind",
    device_name: str = "",
) -> User:
    """Shared bind-existing checks. SSO passes ``forbid_admin=True``; WeChat keeps False.

    ``login_purpose`` is reserved for callers (sso_bind vs wechat_bind); this helper
    does not write identity rows either way.
    """
    _ = login_purpose
    ip = request_ip(config, request)
    name = (username or "").strip()
    window = int(config.login_rate_window_seconds or 60) or 60
    if ip:
        await enforce_limit(db, config, f"login:ip:{ip}", config.login_rate_limit_ip, window)
    if name:
        await enforce_limit(db, config, f"login:user:{name.lower()}", config.login_rate_limit_user, window)
    candidate = await lookup_bind_user(db, name) if name else None
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
    try:
        assert_login_allowed(user)
    except AccountError:
        if use_captcha:
            await captcha.clear_failures(db, config, ip, name)
        raise
    if use_captcha:
        await captcha.clear_failures(db, config, ip, name)
    await clear_lockout(db, config, user, name)
    if forbid_admin and user.is_admin:
        raise account_error(403, "SSO_ADMIN_FORBIDDEN")

    needs_mfa = bool(config.two_factor_enabled and await is_enabled(db, user.id))
    factor_given = bool((code or "").strip() or (recovery_code or "").strip() or (email_code or "").strip())
    if needs_mfa and not factor_given:
        raise await mfa_required(db, user, device_name or "", config)
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
    return user


__all__ = ["lookup_bind_user", "verify_bind_target"]
