from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

TTL_SECONDS = 300
MAX_ATTEMPTS = 5


def _h(raw: str) -> str:
    return hashlib.sha256(("challenge:" + (raw or "")).encode("utf-8")).hexdigest()


def password_fingerprint(hashed_password: Optional[str]) -> str:
    return hashlib.sha256(("pw:" + (hashed_password or "")).encode("utf-8")).hexdigest()[:32]


@dataclass
class Challenge:
    user_id: uuid.UUID
    pw_fp: str
    expires_at: float
    device_name: str = ""
    attempts: int = 0
    passed: bool = False
    method: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)


class ChallengeStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Challenge] = {}

    def create(
        self,
        user_id: uuid.UUID,
        hashed_password: str,
        device_name: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> str:
        raw = secrets.token_urlsafe(32)
        now = time.monotonic()
        ttl = TTL_SECONDS if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._purge_expired_unlocked(now)
            self._items[_h(raw)] = Challenge(
                user_id=user_id,
                pw_fp=password_fingerprint(hashed_password),
                expires_at=now + ttl,
                device_name=device_name or "",
            )
        return raw

    def _purge_expired_unlocked(self, now: float) -> None:
        for key in [key for key, item in self._items.items() if item.expires_at <= now]:
            del self._items[key]

    def get(self, raw: Optional[str]) -> Optional[Challenge]:
        if not raw or len(raw) > 256:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._items.get(_h(raw.strip()))
            if item is None or item.expires_at <= now:
                self._items.pop(_h(raw.strip()), None)
                return None
            return item

    def discard(self, raw: Optional[str]) -> None:
        if not raw:
            return
        with self._lock:
            self._items.pop(_h(raw.strip()), None)

    def discard_user(self, user_id: uuid.UUID) -> None:
        with self._lock:
            for key in [key for key, item in self._items.items() if item.user_id == user_id]:
                del self._items[key]


challenge_store = ChallengeStore()


# --- 0.2.2: storage-agnostic API -------------------------------------------------
# ``state_backend="db"`` keeps challenges in ``auth.two_factor_challenges`` so the
# second login step works across processes; ``"memory"`` uses ``challenge_store``.
# ``challenge_store`` stays importable (hosts call ``discard_user`` on it).


def _db_mode(config) -> bool:
    return config is not None and config.use_db_state()


async def create_challenge(db, config, user_id: uuid.UUID, hashed_password: str, device_name: str, ttl: int) -> str:
    if not _db_mode(config):
        return challenge_store.create(user_id, hashed_password, device_name=device_name, ttl_seconds=ttl)
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, insert

    from account_kit.models import TwoFactorChallenge
    from account_kit.state import run_independent

    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    values = {
        "token_hash": _h(raw),
        "user_id": user_id,
        "pw_fp": password_fingerprint(hashed_password),
        "device_name": (device_name or "")[:128],
        "attempts": 0,
        "passed": False,
        "expires_at": now + timedelta(seconds=ttl),
    }

    async def work(conn):
        await conn.execute(delete(TwoFactorChallenge).where(TwoFactorChallenge.expires_at < now))
        await conn.execute(insert(TwoFactorChallenge).values(**values))

    await run_independent(db, work)
    return raw


async def load_challenge(db, config, raw: Optional[str]) -> Optional[Challenge]:
    if not _db_mode(config):
        return challenge_store.get(raw)
    if not raw or len(raw) > 256:
        return None
    from datetime import datetime, timezone

    from sqlalchemy import select

    from account_kit.models import TwoFactorChallenge

    result = await db.execute(select(TwoFactorChallenge).where(TwoFactorChallenge.token_hash == _h(raw.strip())))
    row = result.scalars().first()
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    left = (expires - datetime.now(timezone.utc)).total_seconds()
    if left <= 0:
        await discard_challenge(db, config, raw)
        return None
    return Challenge(
        user_id=row.user_id,
        pw_fp=row.pw_fp,
        expires_at=time.monotonic() + left,
        device_name=row.device_name or "",
        attempts=int(row.attempts or 0),
        passed=bool(row.passed),
        method=row.method,
    )


async def save_challenge(db, config, raw: str, item: Challenge) -> None:
    """Persist ``attempts`` / ``passed`` / ``method`` (memory items are live objects)."""
    if not _db_mode(config):
        return
    from sqlalchemy import update

    from account_kit.models import TwoFactorChallenge
    from account_kit.state import run_independent

    stmt = (
        update(TwoFactorChallenge)
        .where(TwoFactorChallenge.token_hash == _h(raw.strip()))
        .values(attempts=item.attempts, passed=item.passed, method=item.method)
    )

    async def work(conn):
        await conn.execute(stmt)

    await run_independent(db, work)


async def discard_challenge(db, config, raw: Optional[str]) -> None:
    if not raw:
        return
    challenge_store.discard(raw)
    if not _db_mode(config):
        return
    from sqlalchemy import delete

    from account_kit.models import TwoFactorChallenge
    from account_kit.state import run_independent

    stmt = delete(TwoFactorChallenge).where(TwoFactorChallenge.token_hash == _h(raw.strip()))

    async def work(conn):
        await conn.execute(stmt)

    await run_independent(db, work)


async def discard_user_challenges(db, config, user_id) -> None:
    """Runs in the caller's transaction (commits with the password change etc.)."""
    challenge_store.discard_user(user_id)
    if not _db_mode(config):
        return
    from sqlalchemy import delete

    from account_kit.models import TwoFactorChallenge

    await db.execute(delete(TwoFactorChallenge).where(TwoFactorChallenge.user_id == user_id))
