from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import get_config
from account_kit.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_db(request: Request):
    agen = request.app.state.account_get_db()
    session = await agen.__anext__()
    try:
        yield session
    finally:
        await agen.aclose()


async def user_from_access_token(db: AsyncSession, raw: Optional[str]):
    credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not raw:
        raise credentials
    config = get_config()
    try:
        payload = jwt.decode(raw, config.jwt_secret, algorithms=[config.jwt_algorithm])
        sub = payload.get("sub")
        user_id = uuid.UUID(str(sub))
    except (JWTError, ValueError, TypeError):
        raise credentials

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    if config.session_mode == "single_device":
        sid = payload.get("sid")
        if not sid or sid != user.current_session_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SESSION_REPLACED")
        now = datetime.now(timezone.utc)
        last = user.session_last_seen_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or now - last > timedelta(seconds=60):
            user.session_last_seen_at = now
            await db.commit()
    return user


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
):
    return await user_from_access_token(db, token or query_token)


async def require_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user
