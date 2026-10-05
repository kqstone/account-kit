import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.admin_schemas import AdminUserPatch, RoleBody, RoleChangeCreate, RoleChangeReview, RolePatch, TierBody, TierPatch
from account_kit.catalog import apply_admin_user_patch, create_role, create_tier, delete_role, delete_tier, patch_role, patch_tier
from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, require_admin
from account_kit.models import Role, RoleChangeRequest, User, UserTier
from account_kit.service import assert_role_code, get_user_by_id, to_response

admin_router = APIRouter(tags=["account-admin"])
public_extra = APIRouter(tags=["auth"])


def _role_dict(row: Role) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "sort_order": row.sort_order,
        "description": row.description,
        "is_default": row.is_default,
        "allow_register": row.allow_register,
    }


def _tier_dict(row: UserTier) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "sort_order": row.sort_order,
        "badge_color": row.badge_color,
        "description": row.description,
        "is_default": row.is_default,
    }


@public_extra.get("/roles")
async def public_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.allow_register.is_(True)).order_by(Role.sort_order, Role.code))
    return [_role_dict(row) for row in result.scalars().all()]


@public_extra.get("/tiers")
async def public_tiers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserTier).order_by(UserTier.sort_order, UserTier.code))
    return [_tier_dict(row) for row in result.scalars().all()]


@public_extra.post("/role-change-requests")
async def request_role_change(
    body: RoleChangeCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not get_config().role_change_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    code = assert_role_code(body.requested_role)
    role = await db.get(Role, code)
    if role is None:
        raise HTTPException(status_code=400, detail="角色不存在")
    if code == current_user.role:
        raise HTTPException(status_code=400, detail="已经是该角色")
    existing = await db.execute(
        select(RoleChangeRequest).where(
            RoleChangeRequest.user_id == current_user.id,
            RoleChangeRequest.status == "pending",
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="已有待审核的角色申请")
    row = RoleChangeRequest(user_id=current_user.id, from_role=current_user.role, to_role=code, status="pending")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "from_role": row.from_role, "to_role": row.to_role, "status": row.status}


@admin_router.get("/roles")
async def list_roles(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).order_by(Role.sort_order, Role.code))
    return [_role_dict(row) for row in result.scalars().all()]


@admin_router.post("/roles", status_code=201)
async def add_role(body: RoleBody, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return _role_dict(await create_role(db, body))


@admin_router.patch("/roles/{code}")
async def edit_role(code: str, body: RolePatch, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return _role_dict(await patch_role(db, code, body))


@admin_router.delete("/roles/{code}", status_code=204)
async def remove_role(code: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await delete_role(db, code)


@admin_router.get("/tiers")
async def list_tiers(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserTier).order_by(UserTier.sort_order, UserTier.code))
    return [_tier_dict(row) for row in result.scalars().all()]


@admin_router.post("/tiers", status_code=201)
async def add_tier(body: TierBody, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return _tier_dict(await create_tier(db, body))


@admin_router.patch("/tiers/{code}")
async def edit_tier(code: str, body: TierPatch, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return _tier_dict(await patch_tier(db, code, body))


@admin_router.delete("/tiers/{code}", status_code=204)
async def remove_tier(code: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await delete_tier(db, code)


@admin_router.get("/users")
async def list_users(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [await to_response(db, user) for user in result.scalars().all()]


@admin_router.patch("/users/{user_id}")
async def patch_user(
    user_id: str,
    body: AdminUserPatch,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user = await apply_admin_user_patch(db, user, body)
    return await to_response(db, user)


@admin_router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    config = get_config()
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if config.on_deleted is not None:
        await config.on_deleted(db, user)
    await db.delete(user)
    await db.commit()


@admin_router.post("/role-change-requests/{request_id}/review")
async def review_role_change(
    request_id: str,
    body: RoleChangeReview,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="状态无效")
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="申请不存在")
    row = await db.get(RoleChangeRequest, request_uuid)
    if row is None or row.status != "pending":
        raise HTTPException(status_code=404, detail="申请不存在")
    row.status = body.status
    from datetime import datetime, timezone

    row.reviewed_at = datetime.now(timezone.utc)
    row.reviewed_by = admin.id
    if body.status == "approved":
        user = await get_user_by_id(db, row.user_id)
        if user is not None:
            user.role = row.to_role
    await db.commit()
    return {"id": row.id, "status": row.status}
