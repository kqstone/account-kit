from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, user_from_access_token
from account_kit.emailer import send_code_email
from account_kit.otp import OTP_PURPOSES, assert_resend_allowed, create_code, find_valid_code, normalize_email
from account_kit.schemas import (
    ProfileResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    StatusResponse,
    TokenResponse,
    UserProfileUpdate,
    UserResponse,
    VerifyCodeRequest,
)
from account_kit.security import create_access_token
from account_kit.service import (
    email_allowed,
    get_user_by_email,
    login_user,
    register_user,
    reset_password,
    to_response,
    update_profile,
)

router = APIRouter(tags=["auth"])
_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@router.post("/send-code", response_model=StatusResponse)
async def send_code(
    req: SendCodeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(_bearer),
):
    config = get_config()
    if req.purpose not in OTP_PURPOSES:
        raise HTTPException(status_code=400, detail="Invalid purpose")
    email = normalize_email(req.email)
    if req.purpose == "change_password":
        if not token:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        current = await user_from_access_token(db, token)
        if normalize_email(current.email) != email:
            raise HTTPException(status_code=400, detail="只能向当前账号邮箱发送验证码")
    if req.purpose == "register" and not email_allowed(config, email):
        allowed = ", ".join(config.allowed_email_domains)
        raise HTTPException(status_code=400, detail=f"仅允许带有以下后缀的邮箱注册: {allowed}")

    await assert_resend_allowed(db, email, req.purpose)
    existing = await get_user_by_email(db, email)
    should_send = False
    if req.purpose == "register":
        should_send = existing is None
    elif req.purpose == "reset_password":
        should_send = existing is not None and not existing.is_admin
    elif req.purpose == "change_password":
        should_send = True
    if should_send:
        from account_kit.otp import generate_otp

        code = generate_otp()
        await create_code(db, config.code_secret(), email, req.purpose, code)
        if config.mailer is not None:
            await send_code_email(config, email, req.purpose, code, req.language)
        else:
            background_tasks.add_task(send_code_email, config, email, req.purpose, code, req.language)
    return StatusResponse(status="success", detail="验证码已发送")


@router.post("/verify-code", response_model=StatusResponse)
async def verify_code(req: VerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    config = get_config()
    row = await find_valid_code(db, config.code_secret(), req.email, req.purpose, req.code)
    if not row:
        raise HTTPException(status_code=400, detail="验证码错误或已失效")
    if req.purpose == "register" and await get_user_by_email(db, req.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return StatusResponse(status="success", detail="验证码有效")


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await register_user(db, get_config(), payload)
    return await to_response(db, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    username: str = Form(),
    password: str = Form(),
    force: bool = Form(False),
    device_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    _user, token = await login_user(
        db,
        get_config(),
        username=username,
        password=password,
        force=force,
        device_name=device_name,
    )
    return TokenResponse(access_token=token)


@router.post("/reset-password", response_model=StatusResponse)
async def reset(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await reset_password(db, get_config(), payload.email, payload.code, payload.new_password)
    return StatusResponse(status="success", detail="密码重置成功")


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await to_response(db, current_user)


@router.patch("/me", response_model=ProfileResponse)
async def patch_me(
    payload: UserProfileUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    user, username_changed = await update_profile(db, config, current_user, payload)
    body = ProfileResponse(user=await to_response(db, user))
    if username_changed or payload.new_password:
        token = create_access_token(
            config,
            user_id=str(user.id),
            username=user.username,
            role=user.role,
            is_admin=bool(user.is_admin),
            session_id=user.current_session_id,
        )
        body.access_token = token
        body.token_type = "bearer"
    return body


def mount_account(app, get_db, config) -> None:
    from account_kit.config import set_config

    from account_kit.admin_router import admin_router, public_extra

    set_config(config)
    app.state.account_get_db = get_db
    app.include_router(router, prefix=config.api_prefix)
    app.include_router(public_extra, prefix=config.api_prefix)
    app.include_router(admin_router, prefix=config.admin_prefix)
