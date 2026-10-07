"""Short-lived security state shared by rate limits, wrong-code counters and the
login captcha gate.

``state_backend="db"`` (default) keeps fixed-window counters in
``auth.rate_limit_counters`` (atomic upsert, works across processes);
``"memory"`` keeps them in this process like account-kit <= 0.2.1.

Counter writes run in their own short transaction so they persist even when the
request then fails with an HTTPException (the caller's session is rolled back).
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from account_kit.config import AccountKitConfig

MAX_KEY = 255


def _key(raw: str) -> str:
    return (raw or "")[:MAX_KEY]


def engine_of(db: AsyncSession) -> Optional[AsyncEngine]:
    bind = getattr(db, "bind", None)
    if isinstance(bind, AsyncEngine):
        return bind
    if isinstance(bind, AsyncConnection):
        return bind.engine
    return None


async def run_independent(db: AsyncSession, work: Callable[[AsyncConnection], Awaitable[Any]]) -> Any:
    """Run ``work(conn)`` in a separate committed transaction. Falls back to the
    caller's session (and commits it) when the session is not bound to an engine."""
    engine = engine_of(db)
    if engine is None:
        conn = await db.connection()
        result = await work(conn)
        await db.commit()
        return result
    async with engine.begin() as conn:
        return await work(conn)


class MemoryCounters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Tuple[int, float]] = {}

    def hit(self, key: str, window: float, amount: int = 1) -> int:
        now = time.monotonic()
        with self._lock:
            count, expires = self._items.get(key, (0, 0.0))
            if expires <= now:
                count, expires = 0, now + window
            count += amount
            self._items[key] = (count, expires)
            if len(self._items) > 50000:
                for k in [k for k, (_c, e) in self._items.items() if e <= now]:
                    del self._items[k]
            return count

    def get(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            count, expires = self._items.get(key, (0, 0.0))
            return count if expires > now else 0

    def ttl(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            _count, expires = self._items.get(key, (0, 0.0))
            return max(0, int(expires - now)) if expires > now else 0

    def clear(self, keys: Iterable[str]) -> None:
        with self._lock:
            for key in keys:
                self._items.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._items.clear()


memory_counters = MemoryCounters()

_UPSERT = text(
    """
    INSERT INTO auth.rate_limit_counters AS c (key, count, window_start, expires_at)
    VALUES (:key, :amount, now(), now() + make_interval(secs => :window))
    ON CONFLICT (key) DO UPDATE SET
      count = CASE WHEN c.expires_at <= now() THEN :amount ELSE c.count + :amount END,
      window_start = CASE WHEN c.expires_at <= now() THEN now() ELSE c.window_start END,
      expires_at = CASE WHEN c.expires_at <= now()
                        THEN now() + make_interval(secs => :window) ELSE c.expires_at END
    RETURNING count, GREATEST(0, CEIL(EXTRACT(EPOCH FROM (expires_at - now()))))::int AS ttl
    """
)


async def counter_hit(db: AsyncSession, config: AccountKitConfig, key: str, window_seconds: int, amount: int = 1) -> Tuple[int, int]:
    """Increment ``key`` in a fixed window; return (count, seconds left in window)."""
    key = _key(key)
    window = max(1, int(window_seconds or 1))
    if not config.use_db_state():
        count = memory_counters.hit(key, float(window), amount)
        return count, memory_counters.ttl(key)

    async def work(conn):
        row = (await conn.execute(_UPSERT, {"key": key, "amount": amount, "window": float(window)})).first()
        if random.random() < 0.01:
            await conn.execute(text("DELETE FROM auth.rate_limit_counters WHERE expires_at < now() - interval '1 day'"))
        return int(row[0]), int(row[1])

    return await run_independent(db, work)


async def counter_get(db: AsyncSession, config: AccountKitConfig, key: str) -> int:
    key = _key(key)
    if not config.use_db_state():
        return memory_counters.get(key)
    result = await db.execute(
        text("SELECT count FROM auth.rate_limit_counters WHERE key = :key AND expires_at > now()"), {"key": key}
    )
    value = result.scalar()
    return int(value or 0)


async def counter_ttl(db: AsyncSession, config: AccountKitConfig, key: str) -> int:
    key = _key(key)
    if not config.use_db_state():
        return memory_counters.ttl(key)
    result = await db.execute(
        text(
            "SELECT GREATEST(0, CEIL(EXTRACT(EPOCH FROM (expires_at - now()))))::int "
            "FROM auth.rate_limit_counters WHERE key = :key AND expires_at > now()"
        ),
        {"key": key},
    )
    value = result.scalar()
    return int(value or 0)


async def counter_clear(db: AsyncSession, config: AccountKitConfig, *keys: str) -> None:
    cleaned = [_key(k) for k in keys if k]
    if not cleaned:
        return
    if not config.use_db_state():
        memory_counters.clear(cleaned)
        return

    async def work(conn):
        await conn.execute(text("DELETE FROM auth.rate_limit_counters WHERE key = ANY(:keys)"), {"keys": cleaned})

    await run_independent(db, work)


def rate_limited(message: str = "请求过于频繁，请稍后再试", retry_after: int = 0) -> HTTPException:
    detail: Dict[str, Any] = {"code": "RATE_LIMITED", "message": message}
    headers = None
    if retry_after > 0:
        detail["retry_after"] = retry_after
        headers = {"Retry-After": str(retry_after)}
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers=headers)


async def enforce_limit(
    db: AsyncSession,
    config: AccountKitConfig,
    key: str,
    limit: int,
    window_seconds: int,
    message: str = "请求过于频繁，请稍后再试",
) -> None:
    """Count one request against ``key``; 429 RATE_LIMITED once ``limit`` is exceeded. 0 = off."""
    if not limit or int(limit) <= 0 or not key:
        return
    count, ttl = await counter_hit(db, config, key, window_seconds)
    if count > int(limit):
        raise rate_limited(message, ttl)
