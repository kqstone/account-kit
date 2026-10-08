"""Built-in image captcha (opt-in: ``captcha_builtin=True``).

Rendering needs Pillow: ``pip install "account-kit[captcha]"``. Answers are kept
hashed and single-use in ``auth.captcha_challenges`` (``state_backend="db"``) or
in process memory (``"memory"``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import text

from account_kit.config import AccountKitConfig
from account_kit.state import run_independent

# No ambiguous characters: 0/O, 1/I/l
CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_MEMORY_ENTRIES = 10000


def _hash(config: AccountKitConfig, captcha_id: str, answer: str) -> str:
    material = f"captcha:{captcha_id}:{(answer or '').strip().upper()}".encode("utf-8")
    return hmac.new(config.code_secret().encode("utf-8"), material, hashlib.sha256).hexdigest()


def render_image(code: str, width: int = 140, height: int = 48) -> str:
    """PNG as base64. Raises HTTP 501 when Pillow is not installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - depends on the extra
        from account_kit.i18n import account_error

        raise account_error(501, "CAPTCHA_DEPENDENCY_MISSING") from exc
    rng = secrets.SystemRandom()
    img = Image.new("RGB", (width, height), color=(40, 40, 40))
    draw = ImageDraw.Draw(img)
    for _ in range(80):
        draw.point(
            (rng.randint(0, width - 1), rng.randint(0, height - 1)),
            fill=(rng.randint(80, 180), rng.randint(80, 180), rng.randint(80, 180)),
        )
    for _ in range(4):
        draw.line(
            (
                rng.randint(0, width // 3),
                rng.randint(0, height - 1),
                rng.randint(width * 2 // 3, width - 1),
                rng.randint(0, height - 1),
            ),
            fill=(rng.randint(60, 140), rng.randint(60, 140), rng.randint(60, 140)),
            width=1,
        )
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except OSError:
        try:
            font = ImageFont.load_default(size=28)
        except TypeError:  # Pillow < 10.1
            font = ImageFont.load_default()
    step = width // (len(code) + 1)
    for index, char in enumerate(code):
        draw.text(
            (step * (index + 0.4) + rng.randint(-2, 2), rng.randint(6, 14)),
            char,
            font=font,
            fill=(rng.randint(180, 255), rng.randint(180, 255), rng.randint(180, 255)),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class _MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, Tuple[str, float]] = {}

    def put(self, captcha_id: str, answer_hash: str, ttl: int) -> None:
        now = time.monotonic()
        with self._lock:
            for key in [k for k, (_h, exp) in self._items.items() if exp <= now]:
                del self._items[key]
            if len(self._items) >= MAX_MEMORY_ENTRIES:
                oldest = min(self._items, key=lambda k: self._items[k][1])
                del self._items[oldest]
            self._items[captcha_id] = (answer_hash, now + ttl)

    def pop(self, captcha_id: str) -> Optional[str]:
        with self._lock:
            item = self._items.pop(captcha_id, None)
        if item is None or item[1] <= time.monotonic():
            return None
        return item[0]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


memory_store = _MemoryStore()


def _ttl(config: AccountKitConfig) -> int:
    return max(30, int(config.captcha_ttl_seconds or 300))


async def create_captcha(db, config: AccountKitConfig) -> dict:
    """``{"captcha_id", "image_base64", "expires_in"}`` (same shape the hosts used)."""
    length = min(8, max(3, int(config.captcha_length or 4)))
    code = "".join(secrets.choice(CHARSET) for _ in range(length))
    captcha_id = uuid.uuid4().hex
    ttl = _ttl(config)
    image = render_image(code)
    digest = _hash(config, captcha_id, code)
    if config.use_db_state():
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        async def work(conn):
            await conn.execute(
                text(
                    "INSERT INTO auth.captcha_challenges (id, answer_hash, expires_at) VALUES (:id, :h, :exp)"
                ),
                {"id": captcha_id, "h": digest, "exp": expires},
            )
            if secrets.randbelow(50) == 0:
                await conn.execute(text("DELETE FROM auth.captcha_challenges WHERE expires_at < now()"))

        await run_independent(db, work)
    else:
        memory_store.put(captcha_id, digest, ttl)
    return {"captcha_id": captcha_id, "image_base64": image, "expires_in": ttl}


async def verify_captcha(db, config: AccountKitConfig, captcha_id: Optional[str], code: Optional[str]) -> bool:
    """Consume the captcha; True only on a case-insensitive match before expiry."""
    if not captcha_id or not code or len(str(captcha_id)) > 64:
        return False
    captcha_id = str(captcha_id)
    if config.use_db_state():

        async def work(conn):
            row = (
                await conn.execute(
                    text(
                        "DELETE FROM auth.captcha_challenges WHERE id = :id "
                        "RETURNING answer_hash, expires_at > now() AS live"
                    ),
                    {"id": captcha_id},
                )
            ).first()
            return row

        row = await run_independent(db, work)
        if row is None or not row[1]:
            return False
        stored = row[0]
    else:
        stored = memory_store.pop(captcha_id)
        if stored is None:
            return False
    return hmac.compare_digest(stored, _hash(config, captcha_id, str(code)))
