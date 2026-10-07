import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.admin_schemas import (
    AdminUserPatch,
    RoleBody,
    RoleChangeCreate,
    RoleChangeOut,
    RoleChangeReview,
    RolePatch,
    TierBody,
    TierPatch,
)
from account_kit.catalog import apply_admin_user_patch, create_role, create_tier, delete_role, delete_tier, patch_role, patch_tier
from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, require_admin
from account_kit import audit as audit_mod
from account_kit.audit import audit
from account_kit.models import AuthAuditLog, Role, RoleChangeRequest, User, UserTier
from account_kit.service import assert_role_code, delete_user_account, get_user_by_id, tier_of, to_response

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


def _role_change_out(row: RoleChangeRequest) -> RoleChangeOut:
    return RoleChangeOut(
        id=row.id,
        user_id=row.user_id,
        from_role=row.from_role,
        to_role=row.to_role,
        status=row.status,
        created_at=row.created_at,
    )


@public_extra.post("/role-change-requests", response_model=RoleChangeOut)
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
    return _role_change_out(row)


@public_extra.get("/role-change-requests/me", response_model=Optional[RoleChangeOut])
async def my_role_change_request(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not get_config().role_change_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(RoleChangeRequest)
        .where(RoleChangeRequest.user_id == current_user.id, RoleChangeRequest.status == "pending")
        .order_by(RoleChangeRequest.created_at.desc())
        .limit(1)
    )
    row = result.scalars().first()
    if not row:
        return None
    return _role_change_out(row)


@admin_router.get("/roles")
async def list_roles(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).order_by(Role.sort_order, Role.code))
    return [_role_dict(row) for row in result.scalars().all()]


@admin_router.post("/roles", status_code=201)
async def add_role(body: RoleBody, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    out = _role_dict(await create_role(db, body))
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_ROLE_CHANGED, "create", out["code"], body)
    return out


@admin_router.patch("/roles/{code}")
async def edit_role(code: str, body: RolePatch, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    out = _role_dict(await patch_role(db, code, body))
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_ROLE_CHANGED, "update", code, body)
    return out


@admin_router.delete("/roles/{code}", status_code=204)
async def remove_role(code: str, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await delete_role(db, code)
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_ROLE_CHANGED, "delete", code, None)


@admin_router.get("/tiers")
async def list_tiers(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserTier).order_by(UserTier.sort_order, UserTier.code))
    return [_tier_dict(row) for row in result.scalars().all()]


@admin_router.post("/tiers", status_code=201)
async def add_tier(body: TierBody, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    out = _tier_dict(await create_tier(db, body))
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_TIER_CHANGED, "create", out["code"], body)
    return out


@admin_router.patch("/tiers/{code}")
async def edit_tier(code: str, body: TierPatch, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    out = _tier_dict(await patch_tier(db, code, body))
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_TIER_CHANGED, "update", code, body)
    return out


@admin_router.delete("/tiers/{code}", status_code=204)
async def remove_tier(code: str, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await delete_tier(db, code)
    await _catalog_audit(db, request, admin, audit_mod.ADMIN_TIER_CHANGED, "delete", code, None)


@admin_router.get("/users")
async def list_users(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [await to_response(db, user) for user in result.scalars().all()]


@admin_router.patch("/users/{user_id}")
async def patch_user(
    user_id: str,
    body: AdminUserPatch,
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.is_admin is not None:
        await audit(
            db,
            get_config(),
            audit_mod.ADMIN_PROTECTED,
            user_id=user.id,
            request=request,
            meta={"admin_id": str(admin.id), "action": "is_admin", "code": "ADMIN_FLAG_IMMUTABLE"},
        )
    if user.is_admin and (body.is_active is False or (body.approval_status is not None and body.approval_status != "approved")):
        await audit(
            db,
            get_config(),
            audit_mod.ADMIN_PROTECTED,
            user_id=user.id,
            request=request,
            meta={"admin_id": str(admin.id), "action": "deactivate", "code": "ADMIN_DEACTIVATE_FORBIDDEN"},
        )
    tier = await tier_of(db, user.id)
    before = {
        "role": user.role,
        "is_admin": bool(user.is_admin),
        "is_active": bool(user.is_active),
        "approval_status": user.approval_status,
        "tier_code": tier.code if tier else None,
    }
    admin_id = admin.id
    user = await apply_admin_user_patch(db, user, body)
    tier = await tier_of(db, user.id)
    after = {
        "role": user.role,
        "is_admin": bool(user.is_admin),
        "is_active": bool(user.is_active),
        "approval_status": user.approval_status,
        "tier_code": tier.code if tier else None,
    }
    changes = {key: [before[key], after[key]] for key in before if before[key] != after[key]}
    if changes:
        # Losing access or privileges ends refresh-token sessions.
        if (
            (before["is_active"] and not after["is_active"])
            or (before["approval_status"] == "approved" and after["approval_status"] != "approved")
            or before["is_admin"] != after["is_admin"]
            or before["role"] != after["role"]
        ):
            from account_kit.tokens import revoke_user_tokens

            await revoke_user_tokens(db, user.id, "admin")
            await db.commit()
        await audit(
            db,
            get_config(),
            audit_mod.ADMIN_USER_UPDATED,
            user_id=user.id,
            request=request,
            meta={"admin_id": str(admin_id), "changes": changes},
        )
    return await to_response(db, user)


@admin_router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    config = get_config()
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        await audit(
            db,
            config,
            audit_mod.ADMIN_PROTECTED,
            user_id=user.id,
            request=request,
            meta={"admin_id": str(admin.id), "action": "delete", "code": "ADMIN_DELETE_FORBIDDEN"},
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "ADMIN_DELETE_FORBIDDEN", "message": "不能删除管理员账号"},
        )
    target, username, admin_id = user.id, user.username, admin.id
    mode = await delete_user_account(db, config, user)
    await audit(
        db,
        config,
        audit_mod.ADMIN_USER_DELETED,
        user_id=target,
        request=request,
        meta={"admin_id": str(admin_id), "mode": mode, "username": username},
    )


@admin_router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: Optional[str] = None,
    event: Optional[str] = None,
    ip: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Paginated audit log, newest first. ``event`` accepts a comma-separated list."""
    conditions = []
    if user_id:
        try:
            conditions.append(AuthAuditLog.user_id == uuid.UUID(user_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="user_id 无效")
    if event:
        events = [item.strip() for item in event.split(",") if item.strip()]
        if events:
            conditions.append(AuthAuditLog.event.in_(events))
    if ip:
        conditions.append(AuthAuditLog.ip == ip)
    if since:
        conditions.append(AuthAuditLog.created_at >= since)
    if until:
        conditions.append(AuthAuditLog.created_at < until)
    total = await db.scalar(select(func.count()).select_from(AuthAuditLog).where(*conditions))
    result = await db.execute(
        select(AuthAuditLog)
        .where(*conditions)
        .order_by(AuthAuditLog.created_at.desc(), AuthAuditLog.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for row in result.scalars().all():
        try:
            meta = json.loads(row.meta) if row.meta else None
        except ValueError:
            meta = row.meta
        items.append(
            {
                "id": str(row.id),
                "user_id": str(row.user_id) if row.user_id else None,
                "event": row.event,
                "ip": row.ip,
                "device_name": row.device_name,
                "meta": meta,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@admin_router.post("/role-change-requests/{request_id}/review")
async def review_role_change(
    request_id: str,
    body: RoleChangeReview,
    request: Request,
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
    await audit(
        db,
        get_config(),
        audit_mod.ROLE_CHANGE_REVIEWED,
        user_id=row.user_id,
        request=request,
        meta={"admin_id": str(admin.id), "status": row.status, "from": row.from_role, "to": row.to_role},
    )
    return {"id": row.id, "status": row.status}


async def _catalog_audit(db, request, admin, event: str, action: str, code: str, body) -> None:
    data = body.model_dump(exclude_unset=True) if body is not None else None
    await audit(
        db,
        get_config(),
        event,
        user_id=None,
        request=request,
        meta={"admin_id": str(admin.id), "action": action, "code": code, "data": data},
    )
