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

    def create(self, user_id: uuid.UUID, hashed_password: str, device_name: str = "") -> str:
        raw = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._items[_h(raw)] = Challenge(
                user_id=user_id,
                pw_fp=password_fingerprint(hashed_password),
                expires_at=now + TTL_SECONDS,
                device_name=device_name or "",
            )
        return raw

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
