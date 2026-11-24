"""Password + captcha + lockout + approval + optional admin ban + 2FA for bind-existing.

Does not write identity tables. ``MFA_REQUIRED`` leaves the bind ticket unconsumed;
the caller attaches ``bind_ticket`` on the error extra and (for SSO) calls
``attach_mfa_challenge``. SSO 2FA retry is another POST to the host bind-existing
route, not kit ``POST /login/2fa``.

When the host passes ``challenge_token`` + the loaded ``bind_ticket`` row, a
successful second factor sets ``item.passed=True`` and is **not** discarded here.
The same user + same ticket may retry with an empty code (force / reclaim) until
the host finishes bind + tokens and calls ``discard_challenge`` /
``discard_bind_mfa_challenge``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import captcha
from account_kit.approval import assert_login_allowed
from account_kit.audit import request_ip
from account_kit.bind_ticket import PURPOSE_SSO_BIND
from account_kit.config import AccountKitConfig
from account_kit.i18n import AccountError, account_error
from account_kit.lockout import clear_lockout, enforce_not_locked, record_lockout_failure
from account_kit.models import BindTicket, User
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


async def _accept_bind_mfa_challenge(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    *,
    bind_ticket: BindTicket,
    challenge_token: str,
    code: str,
    recovery_code: str,
    email_code: str,
    login_purpose: str,
) -> None:
    """Reuse a server-bound login-2FA challenge for SSO bind-existing.

    Association is the BindTicket row the host loaded (hash / purpose), not a
    client-reported jti. A first successful factor sets ``passed=True`` and is
    left in the store so force / reclaim can retry with an empty code.
    """
    from account_kit.two_factor.challenges import (
        challenge_token_hash,
        discard_challenge,
        load_challenge,
        save_challenge,
    )

    raw = (challenge_token or "").strip()
    item = await load_challenge(db, config, raw)
    if item is None:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    if item.user_id != user.id:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)

    expected_hash = challenge_token_hash(raw)
    if not bind_ticket.mfa_challenge_hash or bind_ticket.mfa_challenge_hash != expected_hash:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    if item.ticket_hash and item.ticket_hash != bind_ticket.ticket_hash:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)

    wanted = (login_purpose or bind_ticket.purpose or PURPOSE_SSO_BIND).strip()
    if bind_ticket.purpose and wanted and bind_ticket.purpose != wanted:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    if item.purpose and wanted and item.purpose != wanted:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    if item.purpose and bind_ticket.purpose and item.purpose != bind_ticket.purpose:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)

    if item.passed:
        return

    factor_given = bool((code or "").strip() or (recovery_code or "").strip() or (email_code or "").strip())
    if not factor_given:
        raise account_error(400, "MFA_CODE_REQUIRED", as_dict=True)
    try:
        method = await verify_second_factor(
            db,
            config,
            user,
            code=code or "",
            recovery_code=recovery_code or "",
            email_code=email_code or "",
            email_purpose=PURPOSE_LOGIN_2FA if (email_code or "").strip() else "",
        )
    except AccountError as exc:
        item.attempts += 1
        left = config.challenge_max_attempts() - item.attempts
        if left <= 0:
            await discard_challenge(db, config, raw)
            raise account_error(401, "MFA_TOO_MANY_ATTEMPTS", as_dict=True) from exc
        await save_challenge(db, config, raw, item)
        raise
    item.passed = True
    item.method = method
    if not item.ticket_hash:
        item.ticket_hash = bind_ticket.ticket_hash
    if not item.purpose:
        item.purpose = bind_ticket.purpose or wanted
    await save_challenge(db, config, raw, item)


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
    challenge_token: str = "",
    bind_ticket: Optional[BindTicket] = None,
) -> User:
    """Shared bind-existing checks. SSO passes ``forbid_admin=True``; WeChat keeps False.

    ``login_purpose`` is compared to the bind ticket's purpose when a
    ``challenge_token`` is reused. This helper does not write identity rows.
    Password / approval / lockout / captcha always run. Do not discard the
    challenge here; the host discards after bind + tokens succeed.
    """
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
    token = (challenge_token or "").strip()
    factor_given = bool((code or "").strip() or (recovery_code or "").strip() or (email_code or "").strip())
    if needs_mfa and token and bind_ticket is not None:
        await _accept_bind_mfa_challenge(
            db,
            config,
            user,
            bind_ticket=bind_ticket,
            challenge_token=token,
            code=code,
            recovery_code=recovery_code,
            email_code=email_code,
            login_purpose=login_purpose,
        )
    elif needs_mfa and not factor_given:
        raise await mfa_required(db, user, device_name or "", config)
    elif needs_mfa and factor_given:
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
