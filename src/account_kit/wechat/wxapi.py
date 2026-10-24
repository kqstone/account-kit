"""WeChat Mini Program HTTP APIs. Never log secrets or raw WeChat bodies."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from account_kit.i18n import account_error

logger = logging.getLogger("account_kit.wechat")

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WXACODE_URL = "https://api.weixin.qq.com/wxa/getwxacodeunlimit"
INVALID_JS_CODES = {40029, 40163}
HTTP_TIMEOUT = 8.0

_token_lock = threading.Lock()
_token_cache: Dict[str, Tuple[str, float]] = {}


def _httpx():
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise account_error(503, "WECHAT_NOT_CONFIGURED") from exc
    return httpx


def _json_errcode(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("errcode")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def code2session(app_id: str, app_secret: str, js_code: str) -> Dict[str, Any]:
    """Exchange ``wx.login`` js_code for openid. Drops ``session_key`` before returning."""
    httpx = _httpx()
    params = {
        "appid": app_id,
        "secret": app_secret,
        "js_code": js_code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(CODE2SESSION_URL, params=params)
    except Exception:
        logger.warning("account-kit wechat code2session network error")
        raise account_error(401, "WECHAT_CODE_INVALID")
    try:
        payload = response.json()
    except Exception:
        raise account_error(401, "WECHAT_CODE_INVALID")
    err = _json_errcode(payload)
    if err:
        if err in INVALID_JS_CODES:
            raise account_error(401, "WECHAT_CODE_INVALID")
        logger.warning("account-kit wechat code2session errcode=%s", err)
        raise account_error(401, "WECHAT_CODE_INVALID")
    openid = (payload.get("openid") or "").strip()
    if not openid:
        raise account_error(401, "WECHAT_CODE_INVALID")
    unionid = (payload.get("unionid") or "").strip() or None
    return {"openid": openid, "unionid": unionid}


async def _access_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    with _token_lock:
        cached = _token_cache.get(app_id)
        if cached and cached[1] > now + 30:
            return cached[0]
    httpx = _httpx()
    params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Official docs use GET; POST with the same query also works.
            response = await client.get(TOKEN_URL, params=params)
    except Exception:
        logger.warning("account-kit wechat access_token network error")
        raise account_error(502, "WECHAT_QR_FAILED")
    try:
        payload = response.json()
    except Exception:
        raise account_error(502, "WECHAT_QR_FAILED")
    err = _json_errcode(payload)
    token = (payload.get("access_token") or "").strip()
    if err or not token:
        logger.warning("account-kit wechat access_token errcode=%s", err)
        raise account_error(502, "WECHAT_QR_FAILED")
    expires = int(payload.get("expires_in") or 7200)
    # Expire 5 minutes early.
    with _token_lock:
        _token_cache[app_id] = (token, now + max(60, expires - 300))
    return token


def _looks_like_json(data: bytes) -> bool:
    stripped = data.lstrip()
    return stripped[:1] in (b"{", b"[")


async def get_wxacode_unlimit(
    app_id: str,
    app_secret: str,
    *,
    scene: str,
    page: str,
    env_version: str,
    check_path: bool,
    width: int = 280,
) -> bytes:
    token = await _access_token(app_id, app_secret)
    httpx = _httpx()
    body = {
        "scene": scene,
        "page": page,
        "env_version": env_version or "release",
        "check_path": bool(check_path),
        "width": int(width or 280),
    }
    url = f"{WXACODE_URL}?access_token={token}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(url, json=body)
    except Exception:
        logger.warning("account-kit wechat getwxacodeunlimit network error")
        raise account_error(502, "WECHAT_QR_FAILED")
    data = response.content or b""
    if not data:
        raise account_error(502, "WECHAT_QR_FAILED")
    if _looks_like_json(data) or (response.headers.get("content-type") or "").startswith("application/json"):
        try:
            payload = json.loads(data)
        except Exception:
            payload = {}
        err = _json_errcode(payload)
        logger.warning("account-kit wechat getwxacodeunlimit errcode=%s", err)
        raise account_error(502, "WECHAT_QR_FAILED")
    return data


def clear_token_cache() -> None:
    with _token_lock:
        _token_cache.clear()
