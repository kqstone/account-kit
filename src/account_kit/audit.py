"""Write ``auth.auth_audit_logs`` rows. Failures here never break the request."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig
from account_kit.models import AuthAuditLog
from account_kit.state import run_independent

logger = logging.getLogger("account_kit.audit")

# Event names written by account-kit.
LOGIN_SUCCESS = "login_success"
LOGIN_FAILED = "login_failed"
LOGIN_2FA_FAILED = "login_2fa_failed"
TWO_FACTOR_ENABLED = "2fa_enabled"
TWO_FACTOR_DISABLED = "2fa_disabled"
TWO_FACTOR_RESET = "2fa_reset"
RECOVERY_CODES_REGENERATED = "2fa_recovery_regenerated"
PASSWORD_CHANGED = "password_changed"
PASSWORD_RESET = "password_reset"
EMAIL_CHANGED = "email_changed"
LOGOUT = "logout"
REFRESH_REUSE = "refresh_reuse_detected"
ACCOUNT_DELETED = "account_deleted"
CODE_LOCKED = "verification_code_locked"
ADMIN_USER_UPDATED = "admin_user_updated"
ADMIN_USER_DELETED = "admin_user_deleted"
ADMIN_ROLE_CHANGED = "admin_role_changed"
ADMIN_TIER_CHANGED = "admin_tier_changed"
ROLE_CHANGE_REVIEWED = "role_change_reviewed"


def request_ip(config: AccountKitConfig, request) -> str:
    if request is None:
        return ""
    from account_kit.captcha import client_ip

    try:
        return client_ip(config, request) or ""
    except Exception:  # pragma: no cover - host callback failure
        return ""


def _uuid(value) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def audit(
    db: AsyncSession,
    config: AccountKitConfig,
    event: str,
    *,
    user_id=None,
    request=None,
    device_name: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    uid = _uuid(user_id)
    if config.audit_log_enabled:
        values = {
            "id": uuid.uuid4(),
            "user_id": uid,
            "event": (event or "")[:64],
            "ip": request_ip(config, request)[:64] or None,
            "device_name": (device_name or "")[:128] or None,
            "meta": json.dumps(meta, ensure_ascii=False, default=str) if meta else None,
        }

        async def work(conn):
            await conn.execute(insert(AuthAuditLog.__table__).values(**values))

        try:
            await run_independent(db, work)
        except Exception:  # pragma: no cover - audit must not break auth
            logger.exception("account-kit audit write failed (%s)", event)
    if config.on_audit is not None:
        try:
            await config.on_audit(db, event, uid, meta or {})
        except Exception:  # pragma: no cover
            logger.exception("account-kit on_audit hook failed (%s)", event)
