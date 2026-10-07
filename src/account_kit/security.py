from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt

from account_kit.config import AccountKitConfig

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    config: AccountKitConfig,
    *,
    user_id: str,
    username: str,
    role: str,
    is_admin: bool,
    session_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    minutes = config.access_token_expire_minutes
    if is_admin:
        minutes = config.effective_admin_access_token_expire_minutes()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=minutes))
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "is_admin": is_admin,
        "exp": expire,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm or ALGORITHM)
