from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.deps import get_current_user, get_db
from account_kit.sso import service as sso
from account_kit.sso.tokens import jwks_document

router = APIRouter(tags=["sso"])
well_known_router = APIRouter(tags=["sso"])
_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class AuthorizeBody(BaseModel):
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    response_type: Optional[str] = "code"
    scope: Optional[str] = None
    state: Optional[str] = None
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None
    nonce: Optional[str] = None


def _discovery():
    config = get_config()
    sso.assert_sso_ready(config)
    return sso.discovery_document(config)


def _jwks():
    config = get_config()
    sso.assert_sso_ready(config)
    return jwks_document(config)


@well_known_router.get("/.well-known/openid-configuration")
async def root_openid_configuration():
    return _discovery()


@well_known_router.get("/.well-known/jwks.json")
async def root_jwks():
    return _jwks()


@router.get("/.well-known/openid-configuration")
async def prefixed_openid_configuration():
    return _discovery()


@router.get("/.well-known/jwks.json")
async def prefixed_jwks():
    return _jwks()


@router.post("/oauth/authorize")
async def authorize(
    body: AuthorizeBody,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await sso.authorize(db, get_config(), request, current_user, body)
    return JSONResponse(content=payload, headers=sso.NO_STORE)


@router.post("/oauth/token")
async def token(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await sso.exchange_token(db, get_config(), request)
    return JSONResponse(content=payload, headers=sso.NO_STORE)


@router.get("/oauth/userinfo")
async def userinfo(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(_bearer),
):
    return await sso.userinfo(db, get_config(), request, token)
