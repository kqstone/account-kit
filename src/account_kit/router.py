from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import audit as audit_mod
from account_kit import avatar as avatar_mod
from account_kit import captcha
from account_kit.audit import audit, request_ip
from account_kit.config import get_config
from account_kit.deps import get_current_user, get_current_user_allow_query_token, get_db, user_from_access_token
from account_kit.emailer import send_code_email
from account_kit.models import RefreshToken, VerificationCode
from account_kit.otp import (
    OTP_PURPOSES,
    OTP_TTL,
    assert_resend_allowed,
    check_code,
    create_code,
    generate_otp,
    guard_send,
    normalize_email,
    reset_attempts,
    run_before_action,
)
from account_kit.schemas import (
    ChangeEmailCodeRequest,
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    LanguageRequest,
    LogoutRequest,
    ProfileResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    StatusResponse,
    TokenResponse,
    UserProfileUpdate,
    UserResponse,
    VerifyCodeRequest,
)
from account_kit.security import create_access_token, verify_password
from account_kit.service import (
    PURPOSE_CHANGE_EMAIL,
    PURPOSE_DELETE_ACCOUNT,
    _clear_session,
    assert_email_available,
    change_email,
    change_password,
    delete_user_account,
    email_allowed,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    login_user_tokens,
    register_user,
    reset_password,
    to_response,
    update_profile,
)
from account_kit.lockout import clear_lockout, enforce_not_locked, record_lockout_failure
from account_kit.state import enforce_limit

router = APIRouter(tags=["auth"])
_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
CHANGE_EMAIL_COOLDOWN = timedelta(seconds=60)


async def _deliver(config, background_tasks: BackgroundTasks, email: str, purpose: str, code: str, language: str) -> None:
    # The language is passed through unchanged (as before 0.2.2); the bundled
    # templates fall back to zh for anything but "en".
    if config.mailer is not None:
        await send_code_email(config, email, purpose, code, language)
    else:
        background_tasks.add_task(send_code_email, config, email, purpose, code, language)


@router.post("/send-code", response_model=StatusResponse)
async def send_code(
    req: SendCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(_bearer),
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

    await guard_send(db, config, request, email, req.purpose)
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
        code = generate_otp()
        await create_code(db, config.code_secret(), email, req.purpose, code)
        await reset_attempts(db, config, email, req.purpose)
        await _deliver(config, background_tasks, email, req.purpose, code, req.language)
    return StatusResponse(status="success", detail="验证码已发送")


@router.post("/verify-code", response_model=StatusResponse)
async def verify_code(req: VerifyCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    config = get_config()
    await run_before_action(config, request, "verify_code", {"email": normalize_email(req.email), "purpose": req.purpose})
    await check_code(db, config, req.email, req.purpose, req.code, consume=False)
    if req.purpose == "register" and await get_user_by_email(db, req.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return StatusResponse(status="success", detail="验证码有效")


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    config = get_config()
    ip = request_ip(config, request)
    if ip:
        await enforce_limit(db, config, f"register:ip:{ip}", config.register_rate_limit_ip, config.register_rate_window_seconds)
    if config.before_register is not None:
        await config.before_register(request)
    await run_before_action(config, request, "register", {"email": normalize_email(payload.email)})
    user = await register_user(db, config, payload)
    return await to_response(db, user)


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
async def login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    force: bool = Form(False),
    device_name: str = Form(""),
    trusted_device_token: str = Form(""),
    captcha_id: str = Form(""),
    captcha_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    name = (username or "").strip()
    ip = request_ip(config, request)
    window = config.login_rate_window_seconds
    if ip:
        await enforce_limit(db, config, f"login:ip:{ip}", config.login_rate_limit_ip, window)
    if name:
        await enforce_limit(db, config, f"login:user:{name.lower()}", config.login_rate_limit_user, window)
    candidate = await get_user_by_username(db, name) if name else None
    if candidate is not None and candidate.is_admin and config.admin_login_rate_limit_user:
        await enforce_limit(
            db, config, f"login:admin_user:{name.lower()}", config.admin_login_rate_limit_user, window
        )
    if config.before_login is not None:
        await config.before_login(request, username)
    await enforce_not_locked(db, config, candidate, name)
    use_captcha = captcha.captcha_enabled(config)
    admin_always_captcha = bool(
        use_captcha and config.admin_login_captcha_always and candidate is not None and candidate.is_admin
    )
    if use_captcha:
        await captcha.enforce_login_captcha(
            db, config, ip, name, captcha_id, captcha_code, force=admin_always_captcha
        )
    try:
        user, body = await login_user_tokens(
            db,
            config,
            username=username,
            password=password,
            force=force,
            device_name=device_name,
            trusted_device_token=trusted_device_token,
            ip=ip,
        )
    except HTTPException as exc:
        invalid = exc.status_code == 401 and exc.detail == captcha.INVALID_CREDENTIALS_MESSAGE
        if invalid or exc.status_code == 403:
            meta = {"username": name[:50], "reason": "invalid_credentials" if invalid else str(exc.detail)[:64]}
            if config.audit_admin_login:
                meta["is_admin"] = bool(candidate.is_admin) if candidate is not None else False
            await audit(
                db,
                config,
                audit_mod.LOGIN_FAILED,
                user_id=candidate.id if candidate is not None else None,
                request=request,
                device_name=device_name,
                meta=meta,
            )
        if invalid:
            locked = await record_lockout_failure(db, config, candidate, name)
            if locked is not None:
                if use_captcha:
                    await captcha.record_failure(db, config, ip, name)
                raise locked from exc
        if use_captcha:
            if invalid:
                raise await captcha.invalid_credentials(db, config, ip, name, exc.headers) from exc
            # Password was right (2FA, 409, disabled, pending approval...).
            await captcha.clear_failures(db, config, ip, name)
        raise
    if use_captcha:
        await captcha.clear_failures(db, config, ip, name)
    await clear_lockout(db, config, user, name)
    success_meta = {"is_admin": bool(user.is_admin)} if config.audit_admin_login else None
    await audit(
        db, config, audit_mod.LOGIN_SUCCESS, user_id=user.id, request=request, device_name=device_name, meta=success_meta
    )
    return TokenResponse(**body)


@router.post("/reset-password", response_model=StatusResponse)
async def reset(payload: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    config = get_config()
    ip = request_ip(config, request)
    if ip:
        await enforce_limit(
            db, config, f"reset_password:ip:{ip}", config.reset_password_rate_limit_ip, config.reset_password_rate_window_seconds
        )
    await run_before_action(config, request, "reset_password", {"email": normalize_email(payload.email)})
    user = await reset_password(db, config, payload.email, payload.code, payload.new_password)
    if user is not None:
        await audit(db, config, audit_mod.PASSWORD_RESET, user_id=user.id, request=request)
    return StatusResponse(status="success", detail="密码重置成功")


@router.post("/change-password", response_model=StatusResponse)
async def change_password_endpoint(
    payload: ChangePasswordRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    await run_before_action(config, request, "change_password", {"user": current_user})
    user_id = current_user.id
    await change_password(
        db,
        config,
        current_user,
        payload.old_password,
        payload.new_password,
        code=payload.code,
    )
    await audit(db, config, audit_mod.PASSWORD_CHANGED, user_id=user_id, request=request)
    return StatusResponse(status="success", detail="密码修改成功")


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
async def refresh_tokens(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Rotate a refresh token. Reusing a rotated token revokes the whole family."""
    from account_kit.tokens import find_token, issue_refresh_token, refresh_error, refresh_expires_in, revoke_family

    config = get_config()
    if not config.refresh_token_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    await run_before_action(config, request, "refresh", {})
    row = await find_token(db, body.refresh_token, lock=True)
    if row is None:
        raise refresh_error("REFRESH_INVALID", "登录已失效，请重新登录")
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        if row.revoked_reason == "rotated":
            family, user_id, sid = row.family_id, row.user_id, row.session_id
            await revoke_family(db, family, "reuse_detected")
            user = await get_user_by_id(db, user_id)
            if user is not None and config.session_mode == "single_device" and sid and user.current_session_id == sid:
                _clear_session(user)
            await db.commit()
            await audit(db, config, audit_mod.REFRESH_REUSE, user_id=user_id, request=request, meta={"family_id": str(family)})
            raise refresh_error("REFRESH_REUSED", "检测到登录凭证被重复使用，已强制下线，请重新登录")
        raise refresh_error("REFRESH_INVALID", "登录已失效，请重新登录")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise refresh_error("REFRESH_EXPIRED", "登录已过期，请重新登录")
    user = await get_user_by_id(db, row.user_id)
    if user is None:
        raise refresh_error("REFRESH_INVALID", "登录已失效，请重新登录")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    if user.approval_status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号尚未通过审批")
    if user.is_admin and config.admin_refresh_disabled:
        raise refresh_error("REFRESH_INVALID", "登录已失效，请重新登录")
    session_id = None
    if config.session_mode == "single_device":
        if not row.session_id or row.session_id != user.current_session_id:
            await revoke_family(db, row.family_id, "session_replaced")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SESSION_REPLACED")
        session_id = row.session_id
        user.session_last_seen_at = now
    raw, new_row = await issue_refresh_token(
        db,
        config,
        user,
        session_id=session_id,
        device_name=row.device_name or "",
        ip=request_ip(config, request),
        family_id=row.family_id,
    )
    row.revoked_at = now
    row.revoked_reason = "rotated"
    row.used_at = now
    row.replaced_by = new_row.id
    token = create_access_token(
        config,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        is_admin=bool(user.is_admin),
        session_id=session_id,
    )
    await db.commit()
    return TokenResponse(access_token=token, refresh_token=raw, refresh_expires_in=refresh_expires_in(config))


async def _logout_body(request: Request) -> LogoutRequest:
    """Lenient: no body, JSON or form all work (pre-0.2.2 host logouts sent none)."""
    data = {}
    try:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            raw = await request.body()
            if raw.strip():
                parsed = await request.json()
                data = parsed if isinstance(parsed, dict) else {}
        elif "form" in ctype:
            form = await request.form()
            data = {key: form.get(key) for key in ("refresh_token", "all_devices")}
    except Exception:
        data = {}
    all_devices = data.get("all_devices")
    if isinstance(all_devices, str):
        all_devices = all_devices.strip().lower() in ("1", "true", "yes", "on")
    token = data.get("refresh_token")
    return LogoutRequest(
        refresh_token=str(token)[:512] if token else None,
        all_devices=bool(all_devices),
    )


async def logout(request: Request, db: AsyncSession = Depends(get_db), token: Optional[str] = Depends(_bearer)):
    """Superset of the dedd host logout: clears the single-device session when the
    access token still owns it, revokes the session's refresh tokens (and the
    given ``refresh_token``'s family), optionally every device. Always 200."""
    from account_kit.tokens import revoke_token_family, revoke_user_tokens

    config = get_config()
    body = await _logout_body(request)
    user = None
    authenticated = False
    sid = None
    if token:
        try:
            payload = jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm], options={"verify_exp": False})
            user = await get_user_by_id(db, str(payload.get("sub") or ""))
            sid = payload.get("sid")
            exp = payload.get("exp")
            fresh = exp is None or float(exp) > datetime.now(timezone.utc).timestamp()
            if user is not None:
                owns_session = config.session_mode != "single_device" or (sid and sid == user.current_session_id)
                authenticated = bool(fresh and owns_session and user.is_active)
        except (JWTError, ValueError, TypeError):
            user = None
    await run_before_action(config, request, "logout", {"user": user})
    revoked = False
    if user is not None and config.session_mode == "single_device" and sid and sid == user.current_session_id:
        _clear_session(user)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.session_id == sid, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc), revoked_reason="logout")
        )
        revoked = True
    if body.refresh_token:
        revoked = await revoke_token_family(db, body.refresh_token, "logout", user_id=user.id if user else None) or revoked
    if body.all_devices and authenticated:
        await revoke_user_tokens(db, user.id, "logout")
        if config.session_mode == "single_device":
            _clear_session(user)
        revoked = True
    if user is not None and config.on_logout is not None:
        await config.on_logout(db, user)
    await db.commit()
    if user is not None or revoked:
        await audit(
            db,
            config,
            audit_mod.LOGOUT,
            user_id=user.id if user is not None else None,
            request=request,
            meta={"all_devices": bool(body.all_devices and authenticated)},
        )
    return {"status": "success"}


async def get_builtin_captcha(request: Request, db: AsyncSession = Depends(get_db)):
    """Built-in image captcha (``captcha_builtin=True``)."""
    from account_kit.captcha_image import create_captcha

    config = get_config()
    await run_before_action(config, request, "captcha", {})
    return await create_captcha(db, config)


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await to_response(db, current_user)


@router.patch("/me", response_model=ProfileResponse)
async def patch_me(
    payload: UserProfileUpdate,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    user, username_changed = await update_profile(db, config, current_user, payload)
    old_email = getattr(user, "_kit_email_changed_from", None)
    if old_email is not None:
        await audit(
            db, config, audit_mod.EMAIL_CHANGED, user_id=user.id, request=request, meta={"from": old_email, "to": user.email, "via": "patch_me"}
        )
    if payload.new_password:
        await audit(db, config, audit_mod.PASSWORD_CHANGED, user_id=user.id, request=request, meta={"via": "patch_me"})
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


async def _cooldown(db: AsyncSession, email: str, purpose: str, window: timedelta) -> None:
    from sqlalchemy import select

    result = await db.execute(
        select(VerificationCode.created_at)
        .where(VerificationCode.email == normalize_email(email), VerificationCode.purpose == purpose)
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    last = result.scalar()
    if last is not None:
        last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < window:
            raise HTTPException(
                status_code=429, detail={"code": "EMAIL_CODE_TOO_FREQUENT", "message": "验证码发送频繁，请稍后再试"}
            )


@router.post("/me/email/send-code")
async def send_change_email_code(
    body: ChangeEmailCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Email a ``change_email`` code to the *new* address (bound to this user)."""
    from account_kit.two_factor.service import mask_email

    config = get_config()
    nxt = await assert_email_available(db, config, current_user, body.new_email)
    if nxt == current_user.email:
        raise HTTPException(status_code=400, detail="新邮箱与当前邮箱相同")
    if body.password is not None and not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    await run_before_action(config, request, "change_email", {"user": current_user, "email": nxt})
    await guard_send(db, config, request, nxt, PURPOSE_CHANGE_EMAIL)
    await _cooldown(db, nxt, PURPOSE_CHANGE_EMAIL, CHANGE_EMAIL_COOLDOWN)
    code = generate_otp()
    await create_code(db, config.code_secret(), nxt, PURPOSE_CHANGE_EMAIL, code, bind=current_user.id)
    await reset_attempts(db, config, nxt, PURPOSE_CHANGE_EMAIL)
    await _deliver(config, background_tasks, nxt, PURPOSE_CHANGE_EMAIL, code, body.language)
    return {
        "status": "success",
        "detail": "验证码已发送",
        "email": mask_email(nxt),
        "expires_in": int(OTP_TTL.total_seconds()),
        "cooldown": int(CHANGE_EMAIL_COOLDOWN.total_seconds()),
    }


@router.post("/me/email", response_model=UserResponse)
async def confirm_change_email(
    body: ChangeEmailRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm with the code sent to the new address (+ current password by default)."""
    config = get_config()
    await run_before_action(config, request, "change_email", {"user": current_user, "email": normalize_email(body.new_email)})
    old = await change_email(db, config, current_user, body.new_email, body.code, body.password)
    await audit(
        db, config, audit_mod.EMAIL_CHANGED, user_id=current_user.id, request=request, meta={"from": old, "to": current_user.email}
    )
    return await to_response(db, current_user)


def _require_self_delete(config) -> None:
    if not config.self_delete_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/me/delete/email-code")
async def send_delete_email_code(
    body: LanguageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2FA accounts may confirm deletion with an emailed code (needs two_factor_email_enabled)."""
    from account_kit.two_factor.service import is_enabled, send_email_code

    config = get_config()
    _require_self_delete(config)
    if not config.two_factor_email_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if not await is_enabled(db, current_user.id):
        raise HTTPException(status_code=400, detail={"code": "TWO_FACTOR_NOT_ENABLED", "message": "两步验证未开启"})
    await run_before_action(config, request, "delete_account", {"user": current_user})
    await guard_send(db, config, request, current_user.email, PURPOSE_DELETE_ACCOUNT)
    return await send_email_code(db, config, current_user, PURPOSE_DELETE_ACCOUNT, body.language or "zh", background_tasks)


async def _delete_me(body: DeleteAccountRequest, request: Request, current_user, db: AsyncSession):
    from account_kit.two_factor.service import is_enabled, verify_second_factor

    config = get_config()
    _require_self_delete(config)
    await run_before_action(config, request, "delete_account", {"user": current_user})
    if not verify_password(body.password or "", current_user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if current_user.is_admin:
        raise HTTPException(
            status_code=400, detail={"code": "ADMIN_SELF_DELETE_FORBIDDEN", "message": "管理员账号不能自助注销"}
        )
    if config.two_factor_enabled and await is_enabled(db, current_user.id):
        code, recovery, email_code = body.code or "", body.recovery_code or "", body.email_code or ""
        if not code and not recovery and not email_code:
            raise HTTPException(status_code=400, detail={"code": "MFA_CODE_REQUIRED", "message": "请输入两步验证码"})
        await verify_second_factor(
            db,
            config,
            current_user,
            code=code,
            recovery_code=recovery,
            email_code=email_code,
            email_purpose=PURPOSE_DELETE_ACCOUNT,
        )
    user_id = current_user.id
    username = current_user.username
    mode = await delete_user_account(db, config, current_user)
    await audit(
        db, config, audit_mod.ACCOUNT_DELETED, user_id=user_id, request=request, meta={"mode": mode, "self": True, "username": username}
    )
    return {"status": "success", "mode": mode}


@router.post("/me/delete")
async def delete_me_post(
    body: DeleteAccountRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _delete_me(body, request, current_user, db)


@router.delete("/me")
async def delete_me(
    body: DeleteAccountRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _delete_me(body, request, current_user, db)


@router.post("/me/avatar", response_model=UserResponse)
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    content = await file.read()
    old = current_user.avatar_path
    path = await avatar_mod.save_avatar(config, current_user.id, content, file.content_type, file.filename)
    current_user.avatar_path = path
    await db.commit()
    await db.refresh(current_user)
    if old and old != path:
        await avatar_mod.delete_avatar(config, old)
    return await to_response(db, current_user)


@router.delete("/me/avatar", response_model=UserResponse)
async def delete_my_avatar(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = get_config()
    await avatar_mod.delete_avatar(config, current_user.avatar_path)
    current_user.avatar_path = None
    await db.commit()
    await db.refresh(current_user)
    return await to_response(db, current_user)


@router.get("/users/{user_id}/avatar")
async def get_user_avatar(
    user_id: uuid.UUID,
    _current_user=Depends(get_current_user_allow_query_token),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    path = user.avatar_path if user is not None else None
    return await avatar_mod.serve_avatar(get_config(), path)


def mount_account(app, get_db, config) -> None:
    from account_kit.config import set_config

    from account_kit.admin_router import admin_router, public_extra
    from account_kit.two_factor.router import admin as two_factor_admin
    from account_kit.two_factor.router import router as two_factor_router

    set_config(config)
    app.state.account_get_db = get_db
    extra = APIRouter(tags=["auth"])
    if config.logout_enabled:
        path = "/" + (config.logout_path or "/logout").strip().lstrip("/")
        extra.add_api_route(path, logout, methods=["POST"])
    if config.captcha_builtin:
        extra.add_api_route("/captcha", get_builtin_captcha, methods=["GET"])
    app.include_router(router, prefix=config.api_prefix)
    app.include_router(extra, prefix=config.api_prefix)
    app.include_router(public_extra, prefix=config.api_prefix)
    app.include_router(admin_router, prefix=config.admin_prefix)
    if config.two_factor_enabled:
        app.include_router(two_factor_router, prefix=config.api_prefix)
        app.include_router(two_factor_admin, prefix=config.admin_prefix)
