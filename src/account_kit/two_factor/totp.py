from __future__ import annotations

import hmac
import time
from typing import Optional

import pyotp

from account_kit.crypto import fernet_for

DIGITS = 6
INTERVAL = 30
VALID_WINDOW = 1
ENC_PREFIX = "enc:"


def generate_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, account_name: str, issuer: str) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL).provisioning_uri(
        name=account_name or "user",
        issuer_name=issuer,
    )


def current_step(now: Optional[float] = None) -> int:
    return int((time.time() if now is None else now) // INTERVAL)


def code_at_step(secret: str, step: int) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL).at(step * INTERVAL)


def normalize_code(code: Optional[str]) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())


def match_step(secret: str, code: Optional[str], last_step: Optional[int] = None, now: Optional[float] = None) -> Optional[int]:
    cleaned = normalize_code(code)
    if len(cleaned) != DIGITS or not secret:
        return None
    base = current_step(now)
    matched = None
    for step in range(base - VALID_WINDOW, base + VALID_WINDOW + 1):
        if last_step is not None and step <= int(last_step):
            continue
        if hmac.compare_digest(code_at_step(secret, step), cleaned):
            matched = step
    return matched


def encrypt_secret(secret: str, material: str) -> str:
    token = fernet_for(material).encrypt(secret.encode("utf-8")).decode("ascii")
    return ENC_PREFIX + token


def decrypt_secret(stored: Optional[str], material: str) -> Optional[str]:
    if not stored or not stored.startswith(ENC_PREFIX):
        return None
    try:
        return fernet_for(material).decrypt(stored[len(ENC_PREFIX) :].encode("ascii")).decode("utf-8")
    except Exception:
        return None
