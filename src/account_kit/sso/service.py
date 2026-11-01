"""OIDC authorize / token / userinfo. Secrets never appear in logs or audit meta."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit import audit as audit_mod
from account_kit.audit import audit, request_ip
from account_kit.config import AccountKitConfig, SsoClientConfig
from account_kit.i18n import account_error, t
from account_kit.models import OAuthAuthorizationCode, User
from account_kit.otp import run_before_action
from account_kit.service import get_user_by_id
from account_kit.sso.tokens import (
    decode_sso_token,
    issue_tokens,
    jwks_document,
    profile_claims,
    sha256_hex,
    user_has_sso_email,
    userinfo_audience,
)
from account_kit.state import enforce_limit

logger = logging.getLogger("account_kit.sso")

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_ALLOWED_SCOPES = {"openid", "email", "profile"}
_DUMMY_SECRET = "account-kit-sso-dummy-client-secret"
_OAUTH_ERROR = {
    "SSO_DISABLED": ("access_denied", 403),
    "SSO_NOT_CONFIGURED": ("server_error", 503),
    "SSO_INVALID_CLIENT": ("invalid_client", 401),
    "SSO_INVALID_REDIRECT": ("invalid_request", 400),
    "SSO_PKCE_INVALID": ("invalid_grant", 400),
    "SSO_CODE_INVALID": ("invalid_grant", 400),
    "SSO_CODE_EXPIRED": ("invalid_grant", 400),
    "SSO_ADMIN_FORBIDDEN": ("access_denied", 403),
    "SSO_EMAIL_REQUIRED": ("access_denied", 403),
    "SSO_UNSUPPORTED_GRANT": ("unsupported_grant_type", 400),
    "SSO_INVALID_SCOPE": ("invalid_scope", 400),
    "SSO_STATE_REQUIRED": ("invalid_request", 400),
    "SSO_INVALID_REQUEST": ("invalid_request", 400),
}


def sso_error(code: str, *, headers: Optional[Mapping[str, str]] = None, no_store: bool = False):
    oauth, status = _OAUTH_ERROR.get(code, ("invalid_request", 400))
    message = t(code)
    extra = {"error": oauth, "error_description": message}
    hdrs = dict(headers or {})
    if code == "SSO_INVALID_CLIENT":
        hdrs.setdefault("WWW-Authenticate", 'Basic realm="oauth"')
    if no_store:
        hdrs["Cache-Control"] = "no-store"
        hdrs["Pragma"] = "no-cache"
    return account_error(status, code, extra=extra, headers=hdrs or None, as_dict=True)


def validate_sso_issuer(config: AccountKitConfig) -> None:
    issuer = (config.sso_issuer or "").strip()
    if not issuer or config.sso_allow_http_issuer:
        return
    if not issuer.lower().startswith("https://"):
        raise RuntimeError("account-kit: sso_issuer must be https (set sso_allow_http_issuer=True in tests)")


def assert_sso_ready(config: AccountKitConfig, *, no_store: bool = False) -> None:
    if not config.sso_idp_enabled:
        raise sso_error("SSO_DISABLED", no_store=no_store)
    if not config.sso_configured():
        raise sso_error("SSO_NOT_CONFIGURED", no_store=no_store)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _secret_ok(provided: Optional[str], expected: Optional[str]) -> bool:
    left = hashlib.sha256((provided or "").encode("utf-8")).digest()
    right = hashlib.sha256((expected if expected is not None else _DUMMY_SECRET).encode("utf-8")).digest()
    matched = hmac.compare_digest(left, right)
    return bool(matched and expected is not None)


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256((verifier or "").encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _pkce_ok(verifier: str, challenge: str) -> bool:
    computed = _pkce_s256(verifier)
    stored = challenge or ""
    if len(computed) != len(stored):
        hmac.compare_digest(computed, computed)
        return False
    return hmac.compare_digest(computed, stored)


def assert_sso_user(user: User) -> None:
    if not user.is_active:
        raise account_error(403, "USER_DISABLED")
    if user.approval_status != "approved":
        raise account_error(403, "ACCOUNT_PENDING")
    if user.is_admin:
        raise sso_error("SSO_ADMIN_FORBIDDEN")
    if not user_has_sso_email(user):
        raise sso_error("SSO_EMAIL_REQUIRED")


def _parse_scope(raw: Optional[str]) -> str:
    parts = [p for p in (raw or "").split() if p]
    if "openid" not in parts:
        raise sso_error("SSO_INVALID_SCOPE")
    unknown = [p for p in parts if p not in _ALLOWED_SCOPES]
    if unknown:
        raise sso_error("SSO_INVALID_SCOPE")
    return " ".join(parts)


def discovery_document(config: AccountKitConfig) -> Dict[str, Any]:
    issuer = config.sso_issuer_value()
    prefix = (config.api_prefix or "/api/auth").rstrip("/") or "/api/auth"
    jwks = f"{issuer}/.well-known/jwks.json" if config.sso_mount_well_known_root else f"{issuer}{prefix}/.well-known/jwks.json"
    algs = ["RS256", "HS256"] if config.sso_alg() == "RS256" else ["HS256"]
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}{prefix}/oauth/authorize",
        "token_endpoint": f"{issuer}{prefix}/oauth/token",
        "userinfo_endpoint": f"{issuer}{prefix}/oauth/userinfo",
        "jwks_uri": jwks,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": algs,
        "scopes_supported": ["openid", "email", "profile"],
        "claims_supported": [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "nonce",
            "email",
            "email_verified",
            "name",
            "preferred_username",
            "username",
        ],
        "authorization_response_iss_parameter_supported": True,
    }


async def invalidate_user_codes(db: AsyncSession, user_id) -> None:
    if user_id is None:
        return
    await db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.user_id == user_id, OAuthAuthorizationCode.consumed_at.is_(None))
        .values(consumed_at=datetime.now(timezone.utc))
    )


async def authorize(db: AsyncSession, config: AccountKitConfig, request, user: User, body) -> Dict[str, Any]:
    assert_sso_ready(config)
    await run_before_action(config, request, "sso_authorize", {"user": user, "client_id": getattr(body, "client_id", None)})
    client_id = (getattr(body, "client_id", None) or "").strip()
    client = config.sso_client(client_id)
    if client is None:
        raise sso_error("SSO_INVALID_CLIENT")
    redirect_uri = getattr(body, "redirect_uri", None) or ""
    if redirect_uri not in (client.redirect_uris or ()):
        raise sso_error("SSO_INVALID_REDIRECT")
    response_type = (getattr(body, "response_type", None) or "code").strip()
    if response_type != "code":
        raise sso_error("SSO_INVALID_REQUEST")
    scope = _parse_scope(getattr(body, "scope", None))
    state = getattr(body, "state", None)
    if state is None or str(state) == "":
        raise sso_error("SSO_STATE_REQUIRED")
    state = str(state)
    if len(state) > 512:
        raise sso_error("SSO_INVALID_REQUEST")
    challenge = (getattr(body, "code_challenge", None) or "").strip()
    method = (getattr(body, "code_challenge_method", None) or "").strip()
    if not config.sso_require_pkce:
        raise sso_error("SSO_PKCE_INVALID")
    if method != "S256" or not (43 <= len(challenge) <= 128):
        raise sso_error("SSO_PKCE_INVALID")
    nonce = getattr(body, "nonce", None)
    if nonce is not None:
        nonce = str(nonce)
        if nonce == "":
            nonce = None
        elif len(nonce) > 256:
            raise sso_error("SSO_INVALID_REQUEST")
    assert_sso_user(user)
    ttl = max(10, int(config.sso_code_ttl_seconds or 60))
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    row = OAuthAuthorizationCode(
        id=uuid4(),
        code_hash=sha256_hex(raw),
        client_id=client.client_id,
        user_id=user.id,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        code_challenge_method="S256",
        nonce=nonce,
        scope=scope,
        expires_at=now + timedelta(seconds=ttl),
        created_ip=(request_ip(config, request) or "")[:64] or None,
    )
    db.add(row)
    await db.commit()
    await audit(
        db,
        config,
        audit_mod.SSO_AUTHORIZE,
        user_id=user.id,
        request=request,
        meta={"client_id": client.client_id},
    )
    return {"code": raw, "state": state, "redirect_uri": redirect_uri, "expires_in": ttl}


def _parse_basic(request) -> Optional[Tuple[str, str]]:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header.split(None, 1)[1].encode("ascii"), validate=True).decode("utf-8")
    except Exception:
        return None
    ident, _sep, secret = raw.partition(":")
    return ident, secret


def _form_str(form: Mapping[str, Any], key: str) -> str:
    value = form.get(key)
    if value is None:
        return ""
    return str(value)


async def exchange_token(db: AsyncSession, config: AccountKitConfig, request) -> Dict[str, Any]:
    assert_sso_ready(config, no_store=True)
    await run_before_action(config, request, "sso_token", {})
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("application/x-www-form-urlencoded", "multipart/form-data"):
        raise sso_error("SSO_INVALID_REQUEST", no_store=True)
    ip = request_ip(config, request)
    window = max(1, int(config.login_rate_window_seconds or 60))
    if ip:
        await enforce_limit(db, config, f"sso:token:ip:{ip}", config.sso_token_rate_limit_ip, window)
    form = await request.form()
    basic = _parse_basic(request)
    form_id = _form_str(form, "client_id")
    form_secret = _form_str(form, "client_secret")
    if basic is not None and (form_id or form_secret):
        raise sso_error("SSO_INVALID_REQUEST", no_store=True)
    if basic is not None:
        client_id, client_secret = basic
    else:
        client_id, client_secret = form_id, form_secret
    client = config.sso_client(client_id)
    expected = client.client_secret if client is not None else None
    if not _secret_ok(client_secret, expected) or client is None:
        raise sso_error("SSO_INVALID_CLIENT", no_store=True)
    await enforce_limit(db, config, f"sso:token:client:{client.client_id}", config.sso_token_rate_limit_client, window)
    grant_type = _form_str(form, "grant_type")
    if grant_type != "authorization_code":
        raise sso_error("SSO_UNSUPPORTED_GRANT", no_store=True)
    raw_code = _form_str(form, "code")
    redirect_uri = _form_str(form, "redirect_uri")
    verifier = _form_str(form, "code_verifier")
    if not raw_code or not redirect_uri:
        raise sso_error("SSO_INVALID_REQUEST", no_store=True)
    digest = sha256_hex(raw_code)
    result = await db.execute(
        select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code_hash == digest).with_for_update()
    )
    row = result.scalars().first()
    now = datetime.now(timezone.utc)
    if row is None:
        raise sso_error("SSO_CODE_INVALID", no_store=True)
    if row.consumed_at is not None:
        if row.access_jti:
            row.replayed_at = now
            await db.commit()
        else:
            await db.commit()
        raise sso_error("SSO_CODE_INVALID", no_store=True)
    row.consumed_at = now
    if _aware(row.expires_at) is not None and _aware(row.expires_at) <= now:
        await db.commit()
        raise sso_error("SSO_CODE_EXPIRED", no_store=True)
    if row.client_id != client.client_id:
        await db.commit()
        raise sso_error("SSO_CODE_INVALID", no_store=True)
    if row.redirect_uri != redirect_uri:
        await db.commit()
        raise sso_error("SSO_INVALID_REDIRECT", no_store=True)
    if not _pkce_ok(verifier, row.code_challenge or ""):
        await db.commit()
        raise sso_error("SSO_PKCE_INVALID", no_store=True)
    user = await get_user_by_id(db, row.user_id)
    if user is None:
        await db.commit()
        raise sso_error("SSO_CODE_INVALID", no_store=True)
    try:
        assert_sso_user(user)
    except Exception:
        await db.commit()
        raise
    access, ident, jti, expires_in = issue_tokens(
        config, client, user, nonce=row.nonce, scope=row.scope or "openid"
    )
    row.access_jti = jti
    await db.commit()
    await audit(
        db,
        config,
        audit_mod.SSO_TOKEN,
        user_id=user.id,
        request=request,
        meta={"client_id": client.client_id},
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "id_token": ident,
        "scope": row.scope or "openid",
    }


async def userinfo(db: AsyncSession, config: AccountKitConfig, request, raw_token: Optional[str]) -> Dict[str, Any]:
    assert_sso_ready(config)
    await run_before_action(config, request, "sso_userinfo", {})
    credentials = account_error(401, "AUTH_INVALID", headers={"WWW-Authenticate": "Bearer"})
    if not raw_token:
        raise credentials
    try:
        claims = decode_sso_token(config, raw_token, audience=userinfo_audience(config.sso_issuer_value()))
    except Exception:
        raise credentials
    if claims.get("token_use") != "access":
        raise credentials
    jti = claims.get("jti")
    if jti:
        result = await db.execute(
            select(OAuthAuthorizationCode.replayed_at).where(OAuthAuthorizationCode.access_jti == str(jti))
        )
        replayed = result.scalar()
        if replayed is not None:
            raise credentials
    try:
        user = await get_user_by_id(db, claims.get("sub"))
    except Exception:
        raise credentials
    if user is None:
        raise credentials
    assert_sso_user(user)
    body = {
        "sub": str(user.id),
        **profile_claims(user),
    }
    return body
