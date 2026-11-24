"""User approval: provision, login gate, admin decision, pending count."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig, get_config
from account_kit.i18n import account_error
from account_kit.models import User

logger = logging.getLogger("account_kit.approval")

ProvisionSource = Literal["sso", "register", "wechat", "admin", "host"]
ApprovalDecision = Literal["approved", "rejected"]


def assert_login_allowed(user: User) -> None:
    """Raise if the account may not sign in (disabled / pending / rejected)."""
    if not user.is_active:
        raise account_error(403, "USER_DISABLED")
    status = (user.approval_status or "approved").strip().lower()
    if status == "pending":
        raise account_error(403, "ACCOUNT_PENDING")
    if status == "rejected":
        reason = (getattr(user, "approval_reason", None) or "").strip()
        if reason:
            raise account_error(
                403,
                "ACCOUNT_REJECTED",
                params={"reason": reason},
                extra={"reason": reason},
                as_dict=True,
                message_key="ACCOUNT_REJECTED_WITH_REASON",
            )
        raise account_error(403, "ACCOUNT_REJECTED")


async def provision_user(
    db: AsyncSession,
    config: Optional[AccountKitConfig] = None,
    *,
    username: str,
    email: str,
    password: Optional[str] = None,
    password_set: Optional[bool] = None,
    role: Optional[str] = None,
    full_name: Optional[str] = None,
    institution: Optional[str] = None,
    source: ProvisionSource = "host",
    approved: Optional[bool] = None,
    commit: bool = True,
) -> User:
    """Create a user honouring the live ``require_approval`` switch.

    ``create_user(approved=True)`` is unchanged; new flows should call this.
    ``source="admin"`` is always approved. ``approved`` is resolved at call time
    from ``config`` (hot-read), never captured at mount.

    ``commit=True`` commits first, then emails admins if pending.
    ``commit=False`` never emails; the host must ``notify_admins_pending`` after
    its own successful commit. ``on_pending_user`` still runs inside the
    transaction (before commit). Mail failures are not business failures.
    """
    from account_kit.service import create_user

    cfg = config if config is not None else get_config()
    if source == "admin":
        approved = True
    elif approved is None:
        approved = not bool(cfg.require_approval)
    user = await create_user(
        db,
        cfg,
        username=username,
        email=email,
        password=password,
        password_set=password_set,
        role=role,
        full_name=full_name,
        institution=institution,
        approved=approved,
        commit=False,
    )
    if user.approval_status == "pending":
        if cfg.on_pending_user is not None:
            await cfg.on_pending_user(db, user)
        from account_kit import audit as audit_mod
        from account_kit.audit import audit

        await audit(db, cfg, audit_mod.USER_PENDING, user_id=user.id, meta={"via": source})
    if commit:
        await db.commit()
        await db.refresh(user)
        if user.approval_status == "pending":
            await notify_admins_pending(cfg, user, via=source)
    return user


def _reason_max(config: AccountKitConfig) -> int:
    try:
        value = int(config.approval_reason_max or 500)
    except (TypeError, ValueError):
        value = 500
    return max(1, value)


async def set_user_approval(
    db: AsyncSession,
    config: Optional[AccountKitConfig],
    user: User,
    *,
    status: str,
    reason: Optional[str] = None,
    decided_by: Optional[str] = None,
    require_reason: bool = True,
    commit: bool = True,
) -> User:
    """Apply an approval decision. Reject requires 1–``approval_reason_max`` chars
    when ``require_reason`` is True (dedicated admin API). Approve clears reason
    and writes ``approved_at`` only on the first pass. Admin targets are refused.

    ``commit=True`` commits first, then emails the user.
    ``commit=False`` never emails; the host must ``notify_user_approval_decision``
    after a successful commit. ``on_approval_decided`` still runs inside the
    transaction. Mail failures are not business failures.
    """
    cfg = config if config is not None else get_config()
    if user.is_admin:
        raise account_error(
            400,
            "ADMIN_DEACTIVATE_FORBIDDEN",
            as_dict=True,
            message_key="ADMIN_DEACTIVATE_FORBIDDEN_APPROVAL",
        )
    wanted = (status or "").strip().lower()
    if wanted not in ("approved", "rejected"):
        raise account_error(400, "STATUS_INVALID")
    now = datetime.now(timezone.utc)
    cleaned = (reason or "").strip()
    if wanted == "rejected":
        if require_reason:
            maximum = _reason_max(cfg)
            if not cleaned:
                raise account_error(400, "REJECT_REASON_REQUIRED")
            if len(cleaned) > maximum:
                raise account_error(400, "REJECT_REASON_REQUIRED")
        user.approval_status = "rejected"
        user.approval_reason = cleaned or None
    else:
        user.approval_status = "approved"
        user.approval_reason = None
        if user.approved_at is None:
            user.approved_at = now
    user.approval_decided_by = (decided_by or "").strip() or None
    user.approval_decided_at = now
    if wanted != "approved":
        from account_kit.service import _clear_session
        from account_kit.tokens import revoke_user_tokens

        _clear_session(user)
        await revoke_user_tokens(db, user.id, "admin")
    if cfg.on_approval_decided is not None:
        await cfg.on_approval_decided(db, user)
    if commit:
        await db.commit()
        await db.refresh(user)
        await notify_user_approval_decision(cfg, user)
    return user


async def count_pending(db: AsyncSession) -> int:
    total = await db.scalar(select(func.count()).select_from(User).where(User.approval_status == "pending"))
    return int(total or 0)


async def notify_admins_pending(config: AccountKitConfig, user: User, *, via: str) -> None:
    """Email admins that ``user`` is pending. Call after the host commits.

    ``provision_user(..., commit=True)`` sends this automatically after commit.
    ``commit=False`` does not send; the host must call this after a successful
    commit. Mail failures are logged and never raised.
    """
    emails = tuple(item.strip() for item in (config.admin_notify_emails or ()) if item and item.strip())
    if not emails:
        return
    context = {
        "username": user.username,
        "email": user.email,
        "via": via,
        "brand": config.brand_name,
        "public_base_url": config.public_base_url or "",
    }
    from account_kit.emailer import send_notice_email

    for address in emails:
        await send_notice_email(config, address, "admin_pending", context=context)


async def notify_user_approval_decision(config: AccountKitConfig, user: User) -> None:
    """Email the user the approval / rejection decision. Call after commit.

    ``set_user_approval(..., commit=True)`` sends this automatically after commit.
    ``commit=False`` does not send. Status and reason are read from ``user``.
    Mail failures are logged and never raised.
    """
    email = (user.email or "").strip()
    if not email:
        return
    status = (user.approval_status or "").strip().lower()
    purpose = "approval_approved" if status == "approved" else "approval_rejected"
    context = {
        "username": user.username,
        "email": email,
        "reason": (user.approval_reason or "").strip(),
        "brand": config.brand_name,
        "public_base_url": config.public_base_url or "",
    }
    from account_kit.emailer import send_notice_email

    await send_notice_email(config, email, purpose, context=context)
