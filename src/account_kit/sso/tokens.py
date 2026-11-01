"""SSO id_token / access_token signing. Independent of the login JWT secret."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
from jose import jwt

from account_kit.config import AccountKitConfig, SsoClientConfig
from account_kit.models import User

_DELETED_EMAIL_SUFFIX = "@deleted.invalid"


def user_has_sso_email(user: User) -> bool:
    email = (user.email or "").strip()
    if not email or "@" not in email:
        return False
    return not email.lower().endswith(_DELETED_EMAIL_SUFFIX)


def profile_claims(user: User) -> Dict[str, Any]:
    email = (user.email or "").strip()
    username = user.username or ""
    name = (user.full_name or "").strip() or username
    return {
        "email": email,
        "email_verified": bool(user_has_sso_email(user)),
        "name": name,
        "preferred_username": username,
        "username": username,
    }


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def load_private_key(pem: str):
    return load_pem_private_key((pem or "").encode("utf-8"), password=None)


def public_jwk(pem: str, kid: str) -> Dict[str, Any]:
    key = load_private_key(pem)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("sso_signing_key_pem must be an RSA private key")
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid or "sso-1",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def _pad_b64(raw: str) -> bytes:
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def jwk_to_public_pem(jwk_dict: Dict[str, Any]) -> str:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    n = int.from_bytes(_pad_b64(jwk_dict["n"]), "big")
    e = int.from_bytes(_pad_b64(jwk_dict["e"]), "big")
    pub = RSAPublicNumbers(e, n).public_key()
    return pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("utf-8")


def public_pem(pem: str) -> str:
    key = load_private_key(pem)
    return key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("utf-8")


def jwks_document(config: AccountKitConfig) -> Dict[str, Any]:
    if config.sso_alg() != "RS256" or not (config.sso_signing_key_pem or "").strip():
        return {"keys": []}
    return {"keys": [public_jwk(config.sso_signing_key_pem, config.sso_signing_kid or "sso-1")]}


def userinfo_audience(issuer: str) -> str:
    return f"{issuer.rstrip('/')}/userinfo"


def _ttl_seconds(config: AccountKitConfig) -> int:
    return max(30, int(config.sso_id_token_ttl_seconds or 300))


def _sign(
    config: AccountKitConfig,
    client: SsoClientConfig,
    claims: Dict[str, Any],
    *,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    alg = config.sso_alg()
    headers = dict(extra_headers or {})
    if alg == "HS256":
        return jwt.encode(claims, client.client_secret, algorithm="HS256", headers=headers or None)
    kid = config.sso_signing_kid or "sso-1"
    headers.setdefault("kid", kid)
    return jwt.encode(claims, config.sso_signing_key_pem, algorithm="RS256", headers=headers)


def issue_tokens(
    config: AccountKitConfig,
    client: SsoClientConfig,
    user: User,
    *,
    nonce: Optional[str],
    scope: str,
) -> Tuple[str, str, str, int]:
    """Return (access_token, id_token, jti, expires_in). Never uses jwt_secret."""
    issuer = config.sso_issuer_value()
    now = datetime.now(timezone.utc)
    expires_in = _ttl_seconds(config)
    now_ts = int(now.timestamp())
    jti = uuid.uuid4().hex
    profile = profile_claims(user)
    common = {
        "iss": issuer,
        "sub": str(user.id),
        "iat": now_ts,
        "exp": now_ts + expires_in,
        "client_id": client.client_id,
        "scope": scope or "openid",
        **profile,
    }
    access_claims = {
        **common,
        "aud": userinfo_audience(issuer),
        "token_use": "access",
        "jti": jti,
    }
    id_claims = {
        **common,
        "aud": client.client_id,
        "token_use": "id",
    }
    if nonce:
        id_claims["nonce"] = nonce
    access = _sign(config, client, access_claims)
    ident = _sign(config, client, id_claims)
    return access, ident, jti, expires_in


def decode_sso_token(
    config: AccountKitConfig,
    token: str,
    *,
    audience: Optional[str] = None,
    client: Optional[SsoClientConfig] = None,
    access_secret: Optional[str] = None,
) -> Dict[str, Any]:
    header = jwt.get_unverified_header(token)
    alg = (header.get("alg") or config.sso_alg()).upper()
    options = {"verify_aud": audience is not None}
    kwargs: Dict[str, Any] = {"algorithms": [alg], "options": options}
    if audience is not None:
        kwargs["audience"] = audience
    issuer = config.sso_issuer_value()
    if issuer:
        kwargs["issuer"] = issuer
    if alg == "HS256":
        secret = access_secret or (client.client_secret if client is not None else None)
        if not secret:
            unverified = jwt.get_unverified_claims(token)
            found = config.sso_client(str(unverified.get("client_id") or ""))
            secret = found.client_secret if found is not None else ""
        return jwt.decode(token, secret or "", **kwargs)
    return jwt.decode(token, public_pem(config.sso_signing_key_pem), **kwargs)


def sha256_hex(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()
