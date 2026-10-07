"""Login captcha gate: after N failed logins (per IP or username) POST /login
requires ``captcha_id`` + ``captcha_code``. Captchas come from the host
(``AccountKitConfig.captcha_verifier``) or from the built-in module
(``captcha_builtin=True``, GET {api_prefix}/captcha).

Failure counts live in ``auth.rate_limit_counters`` (``state_backend="db"``,
fixed window) or in this process (``"memory"``, sliding window, pre-0.2.2)."""

from __future__ import annotations

import inspect
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, status

from account_kit.config import AccountKitConfig
from account_kit.state import counter_clear, counter_get, counter_hit

INVALID_CREDENTIALS_MESSAGE = "Incorrect username or password"


class LoginFailTracker:
    """In-memory sliding-window failure counts keyed by IP and by username."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_ip: Dict[str, Deque[float]] = defaultdict(deque)
        self._by_user: Dict[str, Deque[float]] = defaultdict(deque)

    @staticmethod
    def _prune(q: Deque[float], cutoff: float) -> None:
        while q and q[0] < cutoff:
            q.popleft()

    def _queues(self, ip: str, username: Optional[str]):
        out = []
        if ip:
            out.append(self._by_ip[ip])
        key = (username or "").strip().lower()
        if key:
            out.append(self._by_user[key])
        return out

    def record_failure(self, ip: str, username: Optional[str], window: float) -> None:
        now = time.monotonic()
        with self._lock:
            for q in self._queues(ip, username):
                self._prune(q, now - window)
                q.append(now)

    def clear_failures(self, ip: str, username: Optional[str]) -> None:
        key = (username or "").strip().lower()
        with self._lock:
            if ip:
                self._by_ip.pop(ip, None)
            if key:
                self._by_user.pop(key, None)

    def requires_captcha(self, ip: str, username: Optional[str], threshold: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            for q in self._queues(ip, username):
                self._prune(q, now - window)
                if len(q) >= threshold:
                    return True
        return False

    def clear_all(self) -> None:
        with self._lock:
            self._by_ip.clear()
            self._by_user.clear()


login_fail_tracker = LoginFailTracker()


def captcha_enabled(config: AccountKitConfig) -> bool:
    return config.captcha_verifier is not None or bool(config.captcha_builtin)


def client_ip(config: AccountKitConfig, request) -> str:
    if config.client_ip is not None:
        return config.client_ip(request) or ""
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or ""


def _window(config: AccountKitConfig) -> float:
    return float(max(60, int(config.captcha_fail_window_seconds or 0)))


def _threshold(config: AccountKitConfig) -> int:
    return max(1, int(config.captcha_fail_threshold or 0))


def _keys(ip: str, username: Optional[str]):
    out = []
    if ip:
        out.append(f"login_fail:ip:{ip}")
    name = (username or "").strip().lower()
    if name:
        out.append(f"login_fail:user:{name}")
    return out


async def requires_captcha(db, config: AccountKitConfig, ip: str, username: str) -> bool:
    if not config.use_db_state():
        return login_fail_tracker.requires_captcha(ip, username, _threshold(config), _window(config))
    threshold = _threshold(config)
    for key in _keys(ip, username):
        if await counter_get(db, config, key) >= threshold:
            return True
    return False


async def record_failure(db, config: AccountKitConfig, ip: str, username: str) -> None:
    if not config.use_db_state():
        login_fail_tracker.record_failure(ip, username, _window(config))
        return
    for key in _keys(ip, username):
        await counter_hit(db, config, key, int(_window(config)))


async def clear_failures(db, config: AccountKitConfig, ip: str, username: str) -> None:
    if not config.use_db_state():
        login_fail_tracker.clear_failures(ip, username)
        return
    await counter_clear(db, config, *_keys(ip, username))


async def _verify(db, config: AccountKitConfig, captcha_id: str, captcha_code: str) -> bool:
    if config.captcha_verifier is None:
        from account_kit.captcha_image import verify_captcha

        return await verify_captcha(db, config, captcha_id, captcha_code)
    result = config.captcha_verifier(captcha_id, captcha_code)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


async def enforce_login_captcha(
    db,
    config: AccountKitConfig,
    ip: str,
    username: str,
    captcha_id: str,
    captcha_code: str,
    *,
    force: bool = False,
) -> None:
    """428 CAPTCHA_REQUIRED / 400 CAPTCHA_INVALID once the failure threshold is reached.

    ``force=True`` requires a captcha even below the failure threshold (admin always-on).
    """
    if not force and not await requires_captcha(db, config, ip, username):
        return
    if not captcha_id or not captcha_code:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"code": "CAPTCHA_REQUIRED", "message": "需要图形验证码", "captcha_required": True},
        )
    if not await _verify(db, config, captcha_id, captcha_code):
        # A wrong captcha still counts as a failed attempt.
        await record_failure(db, config, ip, username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CAPTCHA_INVALID", "message": "图形验证码错误或已失效", "captcha_required": True},
        )


async def invalid_credentials(db, config: AccountKitConfig, ip: str, username: str, headers=None) -> HTTPException:
    """Record a failed password and return the 401 (dict detail with ``captcha_required``)."""
    await record_failure(db, config, ip, username)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_CREDENTIALS",
            "message": INVALID_CREDENTIALS_MESSAGE,
            "captcha_required": await requires_captcha(db, config, ip, username),
        },
        headers=headers or {"WWW-Authenticate": "Bearer"},
    )
