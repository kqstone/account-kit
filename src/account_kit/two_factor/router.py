from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db, require_admin
from account_kit.service import complete_login, get_user_by_id
from account_kit.two_factor.challenges import MAX_ATTEMPTS, challenge_store, password_fingerprint
from account_kit.two_factor.service import (
    admin_reset,
    disable,
    enable,
    issue_trusted_device,
    start_setup,
    verify_second_factor,
)

router = APIRouter(tags=["auth"])
admin = APIRouter(tags=["account-admin"])


class CodeBody(BaseModel):
    code: str


class DisableBody(BaseModel):
    password: str
    code: str = ""
    recovery_code: str = ""


@router.post("/2fa/setup")
async def setup(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not get_config().two_factor_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return await start_setup(db, get_config(), current_user)


@router.post("/2fa/enable")
async def enable_2fa(body: CodeBody, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    codes = await enable(db, get_config(), current_user, body.code)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/2fa/disable")
async def disable_2fa(body: DisableBody, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await disable(db, get_config(), current_user, body.password, body.code, body.recovery_code)
    return {"enabled": False}


@router.post("/login/2fa")
async def login_second_factor(
    challenge_token: str = Form(),
    code: str = Form(""),
    recovery_code: str = Form(""),
    force: bool = Form(False),
    device_name: str = Form(""),
    trust_device: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    item = challenge_store.get(challenge_token)
    if item is None:
        raise HTTPException(status_code=401, detail={"code": "MFA_CHALLENGE_INVALID", "message": "验证已失效"})
    user = await get_user_by_id(db, item.user_id)
    if user is None or item.pw_fp != password_fingerprint(user.hashed_password):
        raise HTTPException(status_code=401, detail={"code": "MFA_CHALLENGE_INVALID", "message": "验证已失效"})
    if not item.passed:
        try:
            item.method = await verify_second_factor(db, get_config(), user, code=code, recovery_code=recovery_code)
        except HTTPException as exc:
            item.attempts += 1
            if item.attempts >= MAX_ATTEMPTS:
                challenge_store.discard_user(user.id)
                raise HTTPException(status_code=401, detail={"code": "MFA_TOO_MANY_ATTEMPTS", "message": "尝试次数过多"}) from exc
            detail = exc.detail if isinstance(exc.detail, dict) else {"code": "MFA_CODE_INVALID", "message": str(exc.detail)}
            detail["attempts_left"] = MAX_ATTEMPTS - item.attempts
            raise HTTPException(status_code=exc.status_code, detail=detail) from exc
        item.passed = True
    _user, token = await complete_login(
        db,
        get_config(),
        user,
        force=force,
        device_name=device_name or item.device_name,
    )
    body = {"access_token": token, "token_type": "bearer", "two_factor_method": item.method}
    if trust_device:
        raw, expires = await issue_trusted_device(db, get_config(), user.id, device_name or item.device_name)
        body["trusted_device_token"] = raw
        body["trusted_device_expires_at"] = expires.isoformat()
    return body


@admin.post("/users/{user_id}/2fa/reset", status_code=204)
async def reset_user_2fa(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    await admin_reset(db, user.id)
