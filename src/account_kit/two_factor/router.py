from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, require_admin
from account_kit.service import complete_login, get_user_by_id
from account_kit.two_factor.challenges import MAX_ATTEMPTS, Challenge, challenge_store, password_fingerprint
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
    language: Optional[str] = "zh"


class ChallengeEmailCodeBody(BaseModel):
    challenge_token: str = Field(..., max_length=256)
    language: Optional[str] = "zh"


CHALLENGE_INVALID = {"code": "MFA_CHALLENGE_INVALID", "message": "登录验证已过期，请重新输入密码登录"}


def _factor(body: DisableBody):
    return body.code or "", body.recovery_code or ""


def _require_email_feature() -> None:
    if not get_config().two_factor_email_enabled:
        raise HTTPException(status_code=404, detail="Not found")


async def _before_two_factor(request: Request, user) -> None:
    hook = get_config().before_two_factor
    if hook is not None:
        await hook(request, user)


async def _load_challenge(db: AsyncSession, raw: str) -> "tuple[Challenge, object]":
    item = challenge_store.get(raw)
    if item is None:
        raise HTTPException(status_code=401, detail=dict(CHALLENGE_INVALID))
    user = await get_user_by_id(db, item.user_id)
    if user is None or item.pw_fp != password_fingerprint(user.hashed_password) or not await is_enabled(db, user.id):
        challenge_store.discard(raw)
        raise HTTPException(status_code=401, detail=dict(CHALLENGE_INVALID))
    return item, user


def _require_feature() -> None:
    if not get_config().two_factor_enabled:
        raise HTTPException(status_code=404, detail="Not found")


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
    if body and body.password:
        _require_password(current_user, body.password)
    return await start_setup(db, get_config(), current_user)


@router.post("/2fa/enable")
async def enable_2fa(body: CodeBody, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    codes = await enable(db, get_config(), current_user, body.code)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/2fa/disable")
async def disable_2fa(body: DisableBody, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    code, recovery = _factor(body)
    await disable(db, get_config(), current_user, body.password, code, recovery, body.email_code or "")
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
        raise HTTPException(status_code=400, detail={"code": "TWO_FACTOR_NOT_ENABLED", "message": "两步验证未开启"})
    await _before_two_factor(request, current_user)
    return await send_email_code(db, get_config(), current_user, PURPOSE_DISABLE_2FA, body.language or "zh", background_tasks)


@router.post("/2fa/recovery-codes/regenerate")
async def regenerate_codes(body: DisableBody, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_feature()
    code, recovery = _factor(body)
    codes = await regenerate_recovery_codes(db, get_config(), current_user, body.password, code, recovery)
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
        raise HTTPException(status_code=404, detail={"code": "DEVICE_NOT_FOUND", "message": "设备不存在"})
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
            raise HTTPException(status_code=400, detail={"code": "MFA_CODE_REQUIRED", "message": "请输入验证码"})
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
            detail = exc.detail if isinstance(exc.detail, dict) else {"code": "MFA_CODE_INVALID", "message": str(exc.detail)}
            if detail.get("code") == "EMAIL_UNAVAILABLE":
                raise
            item.attempts += 1
            left = MAX_ATTEMPTS - item.attempts
            if left <= 0:
                challenge_store.discard(challenge_token)
                raise HTTPException(
                    status_code=401, detail={"code": "MFA_TOO_MANY_ATTEMPTS", "message": "验证码错误次数过多，请重新登录"}
                ) from exc
            raise HTTPException(status_code=exc.status_code, detail={**detail, "attempts_left": left}) from exc
        item.passed = True
    _user, token = await complete_login(
        db,
        config,
        user,
        force=force,
        device_name=device_name or item.device_name,
    )
    challenge_store.discard(challenge_token)
    body = {"access_token": token, "token_type": "bearer", "two_factor_method": item.method}
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
    if item.passed:
        raise HTTPException(status_code=400, detail={"code": "MFA_ALREADY_VERIFIED", "message": "已完成验证"})
    await _before_two_factor(request, user)
    return await send_email_code(db, get_config(), user, PURPOSE_LOGIN_2FA, body.language or "zh", background_tasks)


@admin.post("/users/{user_id}/2fa/reset", status_code=204)
async def reset_user_2fa(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    await admin_reset(db, user.id)
