from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig
from account_kit.models import Role, RoleChangeRequest, User, UserTier, UserTierAssignment
from account_kit.otp import consume_code, normalize_email
from account_kit.profile import birth_year_month_to_date, format_birth_year_month, normalize_gender
from account_kit.schemas import RegisterRequest, UserProfileUpdate, UserResponse
from account_kit.security import create_access_token, hash_password, verify_password
from account_kit.seed import default_role, default_tier

ADMIN_LIKE = re.compile(
    r"admin|administrator|sysadmin|system[_\-]?admin|管理员|管理",
    re.IGNORECASE,
)
MAX_DEVICE_NAME = 64


def assert_role_code(code: str) -> str:
    cleaned = (code or "").strip()
    if not cleaned or cleaned.lower() == "admin":
        raise HTTPException(status_code=400, detail="admin 不是角色，请使用后台权限标记")
    if len(cleaned) > 50:
        raise HTTPException(status_code=400, detail="角色代码过长")
    return cleaned


def assert_username(config: AccountKitConfig, username: str) -> str:
    name = (username or "").strip()
    if not name or len(name) > 50:
        raise HTTPException(status_code=400, detail="用户名无效")
    reserved = {item.lower() for item in config.reserved_usernames}
    if name.lower() in reserved:
        raise HTTPException(status_code=400, detail="用户名不可用")
    if config.forbid_admin_like_usernames and ADMIN_LIKE.search(name):
        raise HTTPException(status_code=400, detail="用户名不能包含管理员相关字符")
    return name


def assert_password(config: AccountKitConfig, password: str) -> None:
    if password is None or len(password) < config.password_min_length:
        raise HTTPException(status_code=400, detail="密码过短")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="密码过长")


def sanitize_device_name(raw: Optional[str]) -> str:
    if not raw or not isinstance(raw, str):
        return "未知设备"
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip()
    return (cleaned or "未知设备")[:MAX_DEVICE_NAME]


def email_allowed(config: AccountKitConfig, email: str) -> bool:
    if not config.email_domain_restriction:
        return True
    domains = [item.strip().lower() for item in config.allowed_email_domains if item.strip()]
    if not domains:
        return True
    return normalize_email(email).split("@")[-1] in domains


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalars().first()


async def get_user_by_id(db: AsyncSession, user_id) -> Optional[User]:
    return await db.get(User, user_id)


async def pending_role(db: AsyncSession, user_id) -> Optional[str]:
    result = await db.execute(
        select(RoleChangeRequest)
        .where(RoleChangeRequest.user_id == user_id, RoleChangeRequest.status == "pending")
        .order_by(RoleChangeRequest.created_at.desc())
        .limit(1)
    )
    row = result.scalars().first()
    return row.to_role if row else None


async def tier_of(db: AsyncSession, user_id) -> Optional[UserTier]:
    result = await db.execute(
        select(UserTier)
        .join(UserTierAssignment, UserTierAssignment.tier_code == UserTier.code)
        .where(UserTierAssignment.user_id == user_id)
    )
    found = result.scalars().first()
    if found:
        return found
    return await default_tier(db)


async def to_response(db: AsyncSession, user: User) -> UserResponse:
    tier = await tier_of(db, user.id)
    payload = UserResponse.model_validate(user)
    return payload.model_copy(
        update={
            "pending_role": await pending_role(db, user.id),
            "birth_year_month": format_birth_year_month(user.birth_year_month),
            "has_custom_avatar": bool(user.avatar_path),
            "tier": tier.code if tier else None,
            "tier_name": tier.name if tier else None,
            "tier_badge_color": tier.badge_color if tier else None,
        }
    )


def _session_active(config: AccountKitConfig, user: User) -> bool:
    if not user.current_session_id or not user.session_last_seen_at:
        return False
    last = user.session_last_seen_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last <= timedelta(hours=config.session_active_hours)


def _clear_session(user: User) -> None:
    user.current_session_id = None
    user.session_last_seen_at = None
    user.session_device_name = None


async def register_user(db: AsyncSession, config: AccountKitConfig, payload: RegisterRequest) -> User:
    if not email_allowed(config, payload.email):
        allowed = ", ".join(config.allowed_email_domains)
        raise HTTPException(status_code=400, detail=f"仅允许带有以下后缀的邮箱注册: {allowed}")
    assert_password(config, payload.password)
    username = assert_username(config, payload.username)
    await consume_code(db, config.code_secret(), payload.email, "register", payload.code)

    if await get_user_by_username(db, username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if await get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.role:
        code = assert_role_code(payload.role)
        role = await db.get(Role, code)
        if role is None or not role.allow_register:
            raise HTTPException(status_code=400, detail="角色无效")
    else:
        role = await default_role(db)

    now = datetime.now(timezone.utc)
    approved = not config.require_approval
    user = User(
        username=username,
        email=normalize_email(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        institution=payload.institution,
        gender=normalize_gender(payload.gender),
        birth_year_month=birth_year_month_to_date(payload.birth_year_month),
        role=role.code,
        is_admin=False,
        is_active=True,
        approval_status="approved" if approved else "pending",
        approved_at=now if approved else None,
    )
    db.add(user)
    await db.flush()
    tier = await default_tier(db)
    db.add(UserTierAssignment(user_id=user.id, tier_code=tier.code))
    if config.on_registered is not None:
        await config.on_registered(db, user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(
    db: AsyncSession,
    config: AccountKitConfig,
    *,
    username: str,
    password: str,
    force: bool = False,
    device_name: str = "",
) -> tuple[User, str]:
    user = await get_user_by_username(db, (username or "").strip())
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    if user.approval_status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号尚未通过审批")

    session_id = None
    if config.session_mode == "single_device":
        if _session_active(config, user) and not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ALREADY_LOGGED_IN",
                    "message": "该账号已在其他设备登录",
                    "device_name": user.session_device_name or "未知设备",
                },
            )
        session_id = str(uuid.uuid4())
        user.current_session_id = session_id
        user.session_last_seen_at = datetime.now(timezone.utc)
        user.session_device_name = sanitize_device_name(device_name)

    if config.on_login is not None:
        await config.on_login(db, user)
    token = create_access_token(
        config,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        is_admin=bool(user.is_admin),
        session_id=session_id,
    )
    await db.commit()
    return user, token


async def reset_password(db: AsyncSession, config: AccountKitConfig, email: str, code: str, new_password: str) -> None:
    assert_password(config, new_password)
    await consume_code(db, config.code_secret(), email, "reset_password", code)
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册账号")
    user.hashed_password = hash_password(new_password)
    if config.session_mode == "single_device":
        _clear_session(user)
    if config.on_password_changed is not None:
        await config.on_password_changed(db, user)
    await db.commit()


async def update_profile(
    db: AsyncSession,
    config: AccountKitConfig,
    user: User,
    payload: UserProfileUpdate,
) -> tuple[User, bool]:
    username_changed = False
    if payload.username is not None and payload.username != user.username:
        username = assert_username(config, payload.username)
        existing = await get_user_by_username(db, username)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Username already registered")
        user.username = username
        username_changed = True

    if payload.email is not None and normalize_email(payload.email) != user.email:
        nxt = normalize_email(payload.email)
        existing = await get_user_by_email(db, nxt)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = nxt

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.institution is not None:
        user.institution = payload.institution
    if "gender" in payload.model_fields_set:
        user.gender = normalize_gender(payload.gender)
    if "birth_year_month" in payload.model_fields_set:
        user.birth_year_month = birth_year_month_to_date(payload.birth_year_month)

    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="当前密码错误")
        assert_password(config, payload.new_password)
        await consume_code(db, config.code_secret(), user.email, "change_password", payload.code)
        user.hashed_password = hash_password(payload.new_password)
        if config.session_mode == "single_device":
            _clear_session(user)
        if config.on_password_changed is not None:
            await config.on_password_changed(db, user)

    await db.commit()
    await db.refresh(user)
    return user, username_changed
