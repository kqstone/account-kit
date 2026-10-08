"""Role and tier catalog. Limits stay in the host; this only stores names."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.i18n import account_error
from account_kit.models import Role, User, UserTier, UserTierAssignment
from account_kit.service import assert_role_code


async def _clear_default_role(db: AsyncSession) -> None:
    await db.execute(update(Role).values(is_default=False))


async def _clear_default_tier(db: AsyncSession) -> None:
    await db.execute(update(UserTier).values(is_default=False))


async def create_role(db: AsyncSession, body) -> Role:
    code = assert_role_code(body.code)
    if await db.get(Role, code):
        raise account_error(409, "ROLE_EXISTS")
    if body.is_default:
        await _clear_default_role(db)
    row = Role(
        code=code,
        name=body.name.strip(),
        sort_order=body.sort_order,
        description=body.description,
        is_default=body.is_default,
        allow_register=body.allow_register,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def patch_role(db: AsyncSession, code: str, body) -> Role:
    row = await db.get(Role, code)
    if row is None:
        raise account_error(404, "ROLE_NOT_FOUND")
    if body.name is not None:
        row.name = body.name.strip()
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    if body.description is not None:
        row.description = body.description
    if body.allow_register is not None:
        row.allow_register = body.allow_register
    if body.is_default is True:
        await _clear_default_role(db)
        row.is_default = True
    elif body.is_default is False and row.is_default:
        raise account_error(400, "ROLE_DEFAULT_REQUIRED")
    await db.commit()
    await db.refresh(row)
    return row


async def delete_role(db: AsyncSession, code: str) -> None:
    row = await db.get(Role, code)
    if row is None:
        raise account_error(404, "ROLE_NOT_FOUND")
    if row.is_default:
        raise account_error(400, "ROLE_DEFAULT_DELETE")
    used = await db.scalar(select(func.count()).select_from(User).where(User.role == code))
    if used:
        raise account_error(409, "ROLE_IN_USE")
    await db.delete(row)
    await db.commit()


async def create_tier(db: AsyncSession, body) -> UserTier:
    code = (body.code or "").strip()
    if not code:
        raise account_error(400, "TIER_CODE_INVALID")
    if await db.get(UserTier, code):
        raise account_error(409, "TIER_EXISTS")
    if body.is_default:
        await _clear_default_tier(db)
    row = UserTier(
        code=code,
        name=body.name.strip(),
        sort_order=body.sort_order,
        badge_color=body.badge_color,
        description=body.description,
        is_default=body.is_default,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def patch_tier(db: AsyncSession, code: str, body) -> UserTier:
    row = await db.get(UserTier, code)
    if row is None:
        raise account_error(404, "TIER_NOT_FOUND")
    if body.name is not None:
        row.name = body.name.strip()
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    if body.badge_color is not None:
        row.badge_color = body.badge_color
    if body.description is not None:
        row.description = body.description
    if body.is_default is True:
        await _clear_default_tier(db)
        row.is_default = True
    elif body.is_default is False and row.is_default:
        raise account_error(400, "TIER_DEFAULT_REQUIRED")
    await db.commit()
    await db.refresh(row)
    return row


async def delete_tier(db: AsyncSession, code: str) -> None:
    row = await db.get(UserTier, code)
    if row is None:
        raise account_error(404, "TIER_NOT_FOUND")
    if row.is_default:
        raise account_error(400, "TIER_DEFAULT_DELETE")
    used = await db.scalar(
        select(func.count()).select_from(UserTierAssignment).where(UserTierAssignment.tier_code == code)
    )
    if used:
        raise account_error(409, "TIER_IN_USE")
    await db.delete(row)
    await db.commit()


async def set_user_tier(db: AsyncSession, user: User, tier_code: str) -> None:
    tier = await db.get(UserTier, tier_code)
    if tier is None:
        raise account_error(400, "TIER_NOT_FOUND")
    row = await db.get(UserTierAssignment, user.id)
    if row is None:
        db.add(UserTierAssignment(user_id=user.id, tier_code=tier.code))
    else:
        row.tier_code = tier.code
        row.updated_at = datetime.now(timezone.utc)


async def apply_admin_user_patch(db, user: User, body) -> User:
    if body.is_admin is not None:
        raise account_error(400, "ADMIN_FLAG_IMMUTABLE", as_dict=True)
    if user.is_admin:
        if body.is_active is False:
            raise account_error(400, "ADMIN_DEACTIVATE_FORBIDDEN", as_dict=True)
        if body.approval_status is not None and body.approval_status != "approved":
            raise account_error(
                400, "ADMIN_DEACTIVATE_FORBIDDEN", as_dict=True, message_key="ADMIN_DEACTIVATE_FORBIDDEN_APPROVAL"
            )
    if body.role is not None:
        code = assert_role_code(body.role)
        if await db.get(Role, code) is None:
            raise account_error(400, "ROLE_NOT_FOUND")
        user.role = code
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.approval_status is not None:
        user.approval_status = body.approval_status
        if body.approval_status == "approved" and user.approved_at is None:
            user.approved_at = datetime.now(timezone.utc)
    if body.tier_code is not None:
        await set_user_tier(db, user, body.tier_code)
    losing_access = (body.is_active is False) or (
        body.approval_status is not None and body.approval_status != "approved"
    )
    if losing_access:
        from account_kit.service import _clear_session

        _clear_session(user)
    await db.commit()
    await db.refresh(user)
    return user
