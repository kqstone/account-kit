from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db
from account_kit.otp import normalize_email
from account_kit.schemas import RegisterRequest
from account_kit.wechat import service as wechat

router = APIRouter(tags=["wechat"])


class StartBody(BaseModel):
    device_name: Optional[str] = ""
    force: bool = False


class TicketBody(BaseModel):
    ticket: str = Field(..., min_length=1, max_length=256)


class ScanBody(BaseModel):
    ticket: str = Field(..., min_length=1, max_length=256)
    js_code: str = Field(..., min_length=1, max_length=256)
    # Accepted for host compatibility; the server derives purpose from the ticket.
    purpose: Optional[str] = None


class ConfirmBody(BaseModel):
    ticket: str = Field(..., min_length=1, max_length=256)
    js_code: str = Field(..., min_length=1, max_length=256)
    force: bool = False
    purpose: Optional[str] = None


class BindExistingBody(BaseModel):
    bind_ticket: str = Field(..., min_length=1, max_length=256)
    username: str
    password: str
    force: bool = False
    device_name: Optional[str] = ""
    code: Optional[str] = ""
    recovery_code: Optional[str] = ""
    email_code: Optional[str] = ""
    captcha_id: Optional[str] = ""
    captcha_code: Optional[str] = ""


class WechatRegisterBody(RegisterRequest):
    bind_ticket: str = Field(..., min_length=1, max_length=256)


class UnbindBody(BaseModel):
    password: str
    code: Optional[str] = ""
    recovery_code: Optional[str] = ""
    email_code: Optional[str] = ""


@router.post("/login/wechat/start")
async def start_login(request: Request, db: AsyncSession = Depends(get_db), body: Optional[StartBody] = None):
    payload = body or StartBody()
    return await wechat.start_login(
        db, get_config(), request, device_name=payload.device_name or "", force=bool(payload.force)
    )


@router.get("/login/wechat/status")
async def login_status(ticket: str = "", db: AsyncSession = Depends(get_db)):
    return await wechat.login_status(db, get_config(), ticket)


@router.post("/login/wechat/cancel")
async def cancel_login(body: TicketBody, db: AsyncSession = Depends(get_db)):
    return await wechat.cancel_ticket(db, get_config(), body.ticket)


@router.post("/login/wechat/scan")
async def scan_login(body: ScanBody, request: Request, db: AsyncSession = Depends(get_db)):
    return await wechat.scan_login(db, get_config(), request, ticket_raw=body.ticket, js_code=body.js_code)


@router.post("/login/wechat/confirm")
async def confirm_login(body: ConfirmBody, request: Request, db: AsyncSession = Depends(get_db)):
    return await wechat.confirm_login(
        db, get_config(), request, ticket_raw=body.ticket, js_code=body.js_code, force=bool(body.force)
    )


@router.post("/login/wechat/bind-existing")
async def bind_existing(body: BindExistingBody, request: Request, db: AsyncSession = Depends(get_db)):
    return await wechat.bind_existing(
        db,
        get_config(),
        request,
        bind_ticket=body.bind_ticket,
        username=body.username,
        password=body.password,
        force=bool(body.force),
        device_name=body.device_name or "",
        code=body.code or "",
        recovery_code=body.recovery_code or "",
        email_code=body.email_code or "",
        captcha_id=body.captcha_id or "",
        captcha_code=body.captcha_code or "",
    )


@router.post("/login/wechat/register")
async def register_wechat(body: WechatRegisterBody, request: Request, db: AsyncSession = Depends(get_db)):
    bind_ticket = body.bind_ticket
    payload = RegisterRequest(
        username=body.username,
        email=normalize_email(str(body.email)),
        password=body.password,
        code=body.code,
        full_name=body.full_name,
        institution=body.institution,
        gender=body.gender,
        birth_year_month=body.birth_year_month,
        role=body.role,
        doctor_consent_version=body.doctor_consent_version,
    )
    return await wechat.register_with_wechat(db, get_config(), request, payload, bind_ticket)


@router.get("/wechat/status")
async def wechat_status(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await wechat.bind_status(db, get_config(), current_user)


@router.post("/wechat/bind/start")
async def bind_start(request: Request, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await wechat.start_bind(db, get_config(), request, current_user)


@router.post("/wechat/bind/confirm")
async def bind_confirm(body: ScanBody, request: Request, db: AsyncSession = Depends(get_db)):
    return await wechat.confirm_bind(db, get_config(), request, ticket_raw=body.ticket, js_code=body.js_code)


@router.post("/wechat/unbind")
async def unbind(
    body: UnbindBody, request: Request, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await wechat.unbind(
        db,
        get_config(),
        request,
        current_user,
        password=body.password,
        code=body.code or "",
        recovery_code=body.recovery_code or "",
        email_code=body.email_code or "",
    )
