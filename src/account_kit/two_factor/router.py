from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import audit as audit_mod
from account_kit.audit import audit, request_ip
from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, require_admin
from account_kit.i18n import AccountError, account_error, error_code_of
from account_kit.otp import guard_send
from account_kit.service import complete_login_tokens, get_user_by_id
from account_kit.two_factor.challenges import (
    Challenge,
    discard_challenge,
    load_challenge,
    password_fingerprint,
    save_challenge,
)
from account_kit.two_factor.service import (
    admin_reset,
    device_public,
    PURPOSE_DISABLE_2FA,
    PURPOSE_LOGIN_2FA,
    disable,
    enable,
    is_enabled,
    recovery_codes_remaining,
    send_email_code,
    issue_trusted_device,
    list_trusted_devices,
    regenerate_recovery_codes,
    revoke_all_trusted,
    revoke_trusted_device,
    start_setup,
    status_payload,
    verify_second_factor,
    _require_password,
)

router = APIRouter(tags=["auth"])
admin = APIRouter(tags=["account-admin"])


class CodeBody(BaseModel):
    code: str


class PasswordBody(BaseModel):
    password: Optional[str] = None


class DisableBody(BaseModel):
    password: str
    code: Optional[str] = ""
    recovery_code: Optional[str] = ""
    email_code: Optional[str] = ""


class EmailCodeBody(BaseModel):
    language: Optional[str] = None


class ChallengeEmailCodeBody(BaseModel):
    challenge_token: str = Field(..., max_length=256)
    language: Optional[str] = None


def _factor(body: DisableBody):
    return body.code or "", body.recovery_code or ""


def _require_email_feature() -> None:
    if not get_config().two_factor_email_enabled:
        raise account_error(404, "NOT_FOUND")


async def _before_two_factor(request: Request, user) -> None:
    hook = get_config().before_two_factor
    if hook is not None:
        await hook(request, user)


async def _load_challenge(db: AsyncSession, raw: str) -> "tuple[Challenge, object]":
    config = get_config()
    item = await load_challenge(db, config, raw)
    if item is None:
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    user = await get_user_by_id(db, item.user_id)
    if user is None or item.pw_fp != password_fingerprint(user.hashed_password) or not await is_enabled(db, user.id):
        await discard_challenge(db, config, raw)
        raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
    return item, user


def _require_feature() -> None:
    if not get_config().two_factor_enabled:
        raise account_error(404, "NOT_FOUND")


@router.get("/2fa/status")
async def two_factor_status(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    return await status_payload(db, get_config(), current_user)


@router.post("/2fa/setup")
async def setup(
    body: Optional[PasswordBody] = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_feature()
    config = get_config()
    password = body.password if body else None
    require_pw = bool(password) or (config.admin_setup_require_password and current_user.is_admin)
    if require_pw:
        if not password:
            raise account_error(400, "PASSWORD_REQUIRED", as_dict=True)
        _require_password(current_user, password)
    return await start_setup(db, config, current_user)


@router.post("/2fa/enable")
async def enable_2fa(
    body: CodeBody, request: Request, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_feature()
    codes = await enable(db, get_config(), current_user, body.code)
    await audit(db, get_config(), audit_mod.TWO_FACTOR_ENABLED, user_id=current_user.id, request=request)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/2fa/disable")
async def disable_2fa(
    body: DisableBody, request: Request, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_feature()
    code, recovery = _factor(body)
    user_id = current_user.id
    await disable(db, get_config(), current_user, body.password, code, recovery, body.email_code or "")
    await audit(db, get_config(), audit_mod.TWO_FACTOR_DISABLED, user_id=user_id, request=request)
    return {"enabled": False}


@router.post("/2fa/disable/email-code")
async def disable_email_code(
    body: EmailCodeBody,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Email a code usable as ``email_code`` in /2fa/disable (password still required)."""
    _require_feature()
    _require_email_feature()
    if not await is_enabled(db, current_user.id):
        raise account_error(400, "TWO_FACTOR_NOT_ENABLED", as_dict=True)
    await _before_two_factor(request, current_user)
    await guard_send(db, get_config(), request, current_user.email, PURPOSE_DISABLE_2FA)
    return await send_email_code(db, get_config(), current_user, PURPOSE_DISABLE_2FA, body.language, background_tasks)


@router.post("/2fa/recovery-codes/regenerate")
async def regenerate_codes(
    body: DisableBody, request: Request, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_feature()
    code, recovery = _factor(body)
    codes = await regenerate_recovery_codes(db, get_config(), current_user, body.password, code, recovery)
    await audit(db, get_config(), audit_mod.RECOVERY_CODES_REGENERATED, user_id=current_user.id, request=request)
    return {"status": "success", "recovery_codes": codes}


@router.get("/trusted-devices")
async def trusted_devices(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    rows = await list_trusted_devices(db, current_user.id)
    return {"devices": [device_public(row) for row in rows]}


@router.delete("/trusted-devices/{device_id}")
async def revoke_device(device_id: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    if not await revoke_trusted_device(db, current_user.id, device_id):
        raise account_error(404, "DEVICE_NOT_FOUND", as_dict=True)
    return {"status": "success"}


@router.delete("/trusted-devices")
async def revoke_devices(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    revoked = await revoke_all_trusted(db, current_user.id)
    return {"status": "success", "revoked": revoked}


@router.post("/login/2fa")
async def login_second_factor(
    request: Request,
    challenge_token: str = Form(),
    code: str = Form(""),
    recovery_code: str = Form(""),
    email_code: str = Form(""),
    force: bool = Form(False),
    device_name: str = Form(""),
    trust_device: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """Second login step. Exactly one factor: ``code`` (TOTP), ``recovery_code`` or
    ``email_code`` (sent by /login/2fa/email/send). A 409 ALREADY_LOGGED_IN keeps
    the verified challenge so the client can retry with ``force=true`` and no code."""
    config = get_config()
    item, user = await _load_challenge(db, challenge_token)
    if not item.passed:
        use_email = bool(email_code) and not code and not recovery_code
        if not code and not recovery_code and not use_email:
            raise account_error(400, "MFA_CODE_REQUIRED", as_dict=True)
        await _before_two_factor(request, user)
        try:
            item.method = await verify_second_factor(
                db,
                config,
                user,
                code=code,
                recovery_code=recovery_code,
                email_code=email_code if use_email else "",
                email_purpose=PURPOSE_LOGIN_2FA if use_email else "",
            )
        except HTTPException as exc:
            if error_code_of(exc) == "EMAIL_UNAVAILABLE":
                raise
            if isinstance(exc.detail, dict):
                detail = dict(exc.detail)
            else:
                detail = {"code": "MFA_CODE_INVALID", "message": str(exc.detail)}
            item.attempts += 1
            left = config.challenge_max_attempts() - item.attempts
            await audit(
                db,
                config,
                audit_mod.LOGIN_2FA_FAILED,
                user_id=user.id,
                request=request,
                device_name=device_name or item.device_name,
                meta={"code": detail.get("code"), "attempts": item.attempts},
            )
            if left <= 0:
                await discard_challenge(db, config, challenge_token)
                raise account_error(401, "MFA_TOO_MANY_ATTEMPTS", as_dict=True) from exc
            await save_challenge(db, config, challenge_token, item)
            extra = {k: v for k, v in detail.items() if k not in ("code", "message")}
            extra["attempts_left"] = left
            code = str(detail.get("code") or "MFA_CODE_INVALID")
            if isinstance(exc, AccountError):
                raise account_error(
                    exc.status_code,
                    exc.kit_code,
                    extra=extra,
                    as_dict=True,
                    message_key=exc.message_key,
                    params=exc.kit_params,
                ) from exc
            raise account_error(exc.status_code, code, extra=extra, as_dict=True) from exc
        item.passed = True
        await save_challenge(db, config, challenge_token, item)
    _user, body = await complete_login_tokens(
        db,
        config,
        user,
        force=force,
        device_name=device_name or item.device_name,
        ip=request_ip(config, request),
    )
    await discard_challenge(db, config, challenge_token)
    meta = {"two_factor_method": item.method}
    if config.audit_admin_login:
        meta["is_admin"] = bool(user.is_admin)
    await audit(
        db,
        config,
        audit_mod.LOGIN_SUCCESS,
        user_id=user.id,
        request=request,
        device_name=device_name or item.device_name,
        meta=meta,
    )
    body = {**body, "two_factor_method": item.method}
    if trust_device:
        raw, expires = await issue_trusted_device(db, config, user.id, device_name or item.device_name)
        body["trusted_device_token"] = raw
        body["trusted_device_expires_at"] = expires.isoformat()
    if item.method == "recovery":
        body["recovery_codes_remaining"] = await recovery_codes_remaining(db, user.id)
    return body


@router.post("/login/2fa/email/send")
async def login_email_send(
    body: ChallengeEmailCodeBody,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Email a one-time login code ("跳过 2FA"). Needs a live challenge (password
    already verified); 2FA stays enabled. Submit it as ``email_code`` to /login/2fa."""
    _require_email_feature()
    item, user = await _load_challenge(db, body.challenge_token)
    if user.is_admin and get_config().admin_require_2fa:
        raise account_error(400, "ADMIN_EMAIL_2FA_FORBIDDEN", as_dict=True)
    if item.passed:
        raise account_error(400, "MFA_ALREADY_VERIFIED", as_dict=True)
    await _before_two_factor(request, user)
    await guard_send(db, get_config(), request, user.email, PURPOSE_LOGIN_2FA)
    return await send_email_code(db, get_config(), user, PURPOSE_LOGIN_2FA, body.language, background_tasks)


@admin.post("/users/{user_id}/2fa/reset", status_code=204)
async def reset_user_2fa(
    user_id: str, request: Request, admin_user=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise account_error(404, "USER_NOT_FOUND")
    target = user.id
    admin_id = admin_user.id
    await admin_reset(db, target, get_config())
    await audit(db, get_config(), audit_mod.TWO_FACTOR_RESET, user_id=target, request=request, meta={"admin_id": str(admin_id)})
