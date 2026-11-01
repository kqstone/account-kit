"""Relying-party helpers: discovery (cached), code exchange, userinfo, id_token verify."""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional, Protocol, Union
from urllib.parse import urljoin

import httpx
from jose import jwt
from jose.exceptions import JWTError


class DiscoveryCache(Protocol):
    def get(self, key: str) -> Optional[Dict[str, Any]]: ...

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None: ...


class MemoryDiscoveryCache:
    """Process-local TTL cache. Inject another implementation to share across workers."""

    def __init__(self) -> None:
        self._items: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        item = self._items.get(key)
        if not item:
            return None
        value, expires = item
        if expires <= time.time():
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        self._items[key] = (value, time.time() + max(1, int(ttl)))


_DEFAULT_CACHE = MemoryDiscoveryCache()
CacheArg = Union[DiscoveryCache, bool, None]


def _issuer_key(issuer: str) -> str:
    return (issuer or "").strip().rstrip("/")


def _discovery_url(issuer: str) -> str:
    base = _issuer_key(issuer) + "/"
    return urljoin(base, ".well-known/openid-configuration")


async def discover(
    issuer: str,
    *,
    cache: CacheArg = None,
    ttl: int = 3600,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Fetch the OIDC discovery document. ``cache=False`` skips caching; ``None`` uses the default memory cache."""
    key = _issuer_key(issuer)
    store: Optional[DiscoveryCache]
    if cache is False:
        store = None
    elif cache is None or cache is True:
        store = _DEFAULT_CACHE
    else:
        store = cache
    if store is not None:
        hit = store.get(key)
        if hit is not None:
            return hit
    url = _discovery_url(issuer)
    own = client is None
    http = client or httpx.AsyncClient()
    try:
        response = await http.get(url, timeout=10.0)
        response.raise_for_status()
        doc = response.json()
    finally:
        if own:
            await http.aclose()
    if not isinstance(doc, dict):
        raise ValueError("openid-configuration must be a JSON object")
    if store is not None:
        store.set(key, doc, ttl)
    return doc


async def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    token_endpoint: str = "",
    issuer: str = "",
    auth_method: str = "client_secret_post",
    client: Optional[httpx.AsyncClient] = None,
    cache: CacheArg = None,
) -> Dict[str, Any]:
    endpoint = token_endpoint
    if not endpoint:
        if not issuer:
            raise ValueError("token_endpoint or issuer is required")
        doc = await discover(issuer, cache=cache, client=client)
        endpoint = doc.get("token_endpoint") or ""
    if not endpoint:
        raise ValueError("token_endpoint is missing")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    headers = {"Accept": "application/json"}
    auth = None
    method = (auth_method or "client_secret_post").lower()
    if method == "client_secret_basic":
        auth = (client_id, client_secret)
    else:
        data["client_id"] = client_id
        data["client_secret"] = client_secret
    own = client is None
    http = client or httpx.AsyncClient()
    try:
        response = await http.post(endpoint, data=data, headers=headers, auth=auth, timeout=10.0)
        response.raise_for_status()
        return response.json()
    finally:
        if own:
            await http.aclose()


async def fetch_userinfo(
    *,
    access_token: str,
    userinfo_endpoint: str = "",
    issuer: str = "",
    client: Optional[httpx.AsyncClient] = None,
    cache: CacheArg = None,
) -> Dict[str, Any]:
    endpoint = userinfo_endpoint
    if not endpoint:
        if not issuer:
            raise ValueError("userinfo_endpoint or issuer is required")
        doc = await discover(issuer, cache=cache, client=client)
        endpoint = doc.get("userinfo_endpoint") or ""
    if not endpoint:
        raise ValueError("userinfo_endpoint is missing")
    own = client is None
    http = client or httpx.AsyncClient()
    try:
        response = await http.get(
            endpoint,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    finally:
        if own:
            await http.aclose()


def _jwk_for_token(token: str, jwks: Mapping[str, Any]) -> Dict[str, Any]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    keys = list((jwks or {}).get("keys") or [])
    matched = None
    for item in keys:
        if kid and item.get("kid") != kid:
            continue
        if (item.get("kty") or "RSA") == "RSA":
            matched = item
            if kid:
                break
    if matched is None and len(keys) == 1:
        matched = keys[0]
    if matched is None:
        raise JWTError("no matching JWK")
    return matched


def verify_id_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    nonce: Optional[str] = None,
    client_secret: Optional[str] = None,
    jwks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Verify signature (JWKS / HS256 client_secret) plus iss, aud, exp, nonce."""
    header = jwt.get_unverified_header(token)
    alg = (header.get("alg") or "").upper()
    iss = _issuer_key(issuer)
    kwargs: Dict[str, Any] = {
        "algorithms": [alg] if alg else ["RS256", "HS256"],
        "audience": audience,
        "issuer": iss,
        "options": {"verify_aud": True, "verify_iss": True, "verify_exp": True},
    }
    if alg == "HS256":
        if not client_secret:
            raise JWTError("HS256 id_token requires client_secret")
        claims = jwt.decode(token, client_secret, **kwargs)
    else:
        if not jwks:
            raise JWTError("RS256 id_token requires jwks")
        from account_kit.sso.tokens import jwk_to_public_pem

        key = jwk_to_public_pem(_jwk_for_token(token, jwks))
        claims = jwt.decode(token, key, **kwargs)
    token_nonce = claims.get("nonce")
    if nonce is not None and str(nonce) != str(token_nonce or ""):
        raise JWTError("nonce mismatch")
    if nonce is None and token_nonce:
        raise JWTError("nonce mismatch")
    if claims.get("iss") != iss:
        raise JWTError("invalid issuer")
    aud = claims.get("aud")
    if isinstance(aud, (list, tuple)):
        if audience not in aud:
            raise JWTError("invalid audience")
    elif aud != audience:
        raise JWTError("invalid audience")
    return claims
