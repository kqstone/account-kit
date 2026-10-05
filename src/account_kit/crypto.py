from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def fernet_for(material: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)
