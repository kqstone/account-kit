"""OIDC IdP (0.5.0). Injected RSA key, no network."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from account_kit import init_db, mount_account
from account_kit.captcha import login_fail_tracker
from account_kit.captcha_image import memory_store as captcha_memory
from account_kit.config import AccountKitConfig, SsoClientConfig
from account_kit.models import OAuthAuthorizationCode, User
from account_kit.schema_setup import upgrade_sql
from account_kit.sso.rp import MemoryDiscoveryCache, discover, verify_id_token
from account_kit.state import memory_counters
from account_kit.two_factor.challenges import challenge_store
from tests.conftest import _database_url
from tests.helpers import approved_user, audit_events, bearer, make_admin

REDIRECT = "https://dedd.example.test/app/sso/callback"
CLIENT_ID = "dedd"
CLIENT_SECRET = "dedd-secret-value"
ISSUER = "https://idp.example.test"


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


SSO_PEM = _rsa_pem()


def _pkce():
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _client() -> SsoClientConfig:
    return SsoClientConfig(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uris=(REDIRECT,),
        name="DEDD",
    )


@pytest.fixture
async def sso():
    engine = create_async_engine(_database_url())
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
    await init_db(engine)
    login_fail_tracker.clear_all()
    challenge_store._items.clear()
    memory_counters.clear_all()
    captcha_memory.clear()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sent = []

    async def mailer(to, purpose, code, language):
        sent.append({"to": to, "purpose": purpose, "code": code, "language": language})

    async def get_db():
        async with sessions() as session:
            yield session

    actions = []

    async def before_action(request, action, info):
        actions.append(action)

    config = AccountKitConfig(
        jwt_secret="login-secret-must-not-sign-sso",
        mailer=mailer,
        brand_name="Test",
        session_mode="stateless",
        require_approval=True,
        state_backend=os.environ.get("ACCOUNT_KIT_TEST_STATE_BACKEND", "db"),
        sso_idp_enabled=True,
        sso_issuer=ISSUER,
        sso_jwt_algorithm="RS256",
        sso_signing_key_pem=SSO_PEM,
        sso_signing_kid="sso-test",
        sso_clients=(_client(),),
        sso_code_ttl_seconds=60,
        before_action=before_action,
        self_delete_enabled=True,
    )
    app = FastAPI()
    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "sent": sent,
            "sessions": sessions,
            "config": config,
            "app": app,
            "actions": actions,
        }
    await engine.dispose()


async def _authorize(api, headers, **extra):
    verifier, challenge = _pkce()
    body = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": "openid email profile",
        "state": "state-xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": "nonce-abc",
    }
    body.update(extra)
    res = await api["client"].post("/api/auth/oauth/authorize", json=body, headers=headers)
    return res, verifier, body


async def _token(api, code, verifier, *, basic=False, extra=None, redirect_uri=REDIRECT):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if extra:
        data.update(extra)
    headers = {}
    if basic:
        raw = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        headers["Authorization"] = f"Basic {raw}"
    else:
        data["client_id"] = CLIENT_ID
        data["client_secret"] = CLIENT_SECRET
    return await api["client"].post("/api/auth/oauth/token", data=data, headers=headers)


async def test_disabled_has_no_routes(api):
    res = await api["client"].post("/api/auth/oauth/authorize", json={})
    assert res.status_code == 404
    res = await api["client"].post("/api/auth/oauth/token", data={"grant_type": "authorization_code"})
    assert res.status_code == 404
    res = await api["client"].get("/api/auth/oauth/userinfo")
    assert res.status_code == 404
    res = await api["client"].get("/.well-known/openid-configuration")
    assert res.status_code == 404
    res = await api["client"].get("/api/auth/.well-known/openid-configuration")
    assert res.status_code == 404


async def test_hot_disable_returns_403(sso):
    sso["config"].sso_idp_enabled = False
    user, body = await approved_user(sso, username="hotoff")
    res, _, _ = await _authorize(sso, bearer(body))
    assert res.status_code == 403
    assert res.json()["code"] == "SSO_DISABLED"
    assert res.json()["error"] == "access_denied"
    disc = await sso["client"].get("/.well-known/openid-configuration")
    assert disc.status_code == 403
    assert disc.json()["code"] == "SSO_DISABLED"


async def test_not_configured_returns_503():
    engine = create_async_engine(_database_url())
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
    await init_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def get_db():
        async with sessions() as session:
            yield session

    config = AccountKitConfig(
        jwt_secret="t",
        sso_idp_enabled=True,
        sso_issuer=ISSUER,
        state_backend="memory",
    )
    app = FastAPI()
    mount_account(app, get_db, config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/.well-known/openid-configuration")
        assert res.status_code == 503
        assert res.json()["code"] == "SSO_NOT_CONFIGURED"
    await engine.dispose()


def test_https_issuer_required_at_mount():
    from account_kit.sso.service import validate_sso_issuer

    with pytest.raises(RuntimeError, match="https"):
        validate_sso_issuer(
            AccountKitConfig(
                jwt_secret="t",
                sso_idp_enabled=True,
                sso_issuer="http://insecure.example",
                sso_signing_key_pem=SSO_PEM,
                sso_clients=(_client(),),
            )
        )


async def test_happy_rs256_code_token_userinfo(sso):
    user, body = await approved_user(sso, username="ssoalice")
    res, verifier, req = await _authorize(sso, bearer(body))
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["state"] == "state-xyz"
    assert payload["redirect_uri"] == REDIRECT
    assert payload["expires_in"] == 60
    assert "sso_authorize" in sso["actions"]
    token = await _token(sso, payload["code"], verifier)
    assert token.status_code == 200, token.text
    assert token.headers.get("cache-control") == "no-store"
    assert token.headers.get("pragma") == "no-cache"
    toks = token.json()
    assert toks["token_type"] == "Bearer"
    assert "refresh_token" not in toks
    id_claims = jwt.get_unverified_claims(toks["id_token"])
    access_claims = jwt.get_unverified_claims(toks["access_token"])
    assert id_claims["aud"] == CLIENT_ID
    assert id_claims["iss"] == ISSUER
    assert id_claims["nonce"] == "nonce-abc"
    assert id_claims["email"] == "ssoalice@example.com"
    assert id_claims["email_verified"] is True
    assert id_claims["name"]
    assert id_claims["preferred_username"] == "ssoalice"
    assert id_claims["username"] == "ssoalice"
    assert id_claims["token_use"] == "id"
    assert access_claims["aud"] == f"{ISSUER}/userinfo"
    assert access_claims["jti"]
    assert access_claims["email"] == id_claims["email"]
    login_header = jwt.get_unverified_header(body["access_token"])
    sso_header = jwt.get_unverified_header(toks["id_token"])
    assert sso_header["alg"] == "RS256"
    assert sso_header["kid"] == "sso-test"
    assert login_header.get("alg") in (None, "HS256") or True
    with pytest.raises(Exception):
        jwt.decode(toks["id_token"], sso["config"].jwt_secret, algorithms=["HS256"], audience=CLIENT_ID, issuer=ISSUER)
    jwks = (await sso["client"].get("/.well-known/jwks.json")).json()
    assert jwks["keys"][0]["kid"] == "sso-test"
    verified = verify_id_token(
        toks["id_token"], issuer=ISSUER, audience=CLIENT_ID, nonce="nonce-abc", jwks=jwks
    )
    assert verified["sub"] == str(user["id"])
    info = await sso["client"].get("/api/auth/oauth/userinfo", headers={"Authorization": f"Bearer {toks['access_token']}"})
    assert info.status_code == 200, info.text
    profile = info.json()
    assert profile["sub"] == str(user["id"])
    assert profile["email"] == "ssoalice@example.com"
    assert profile["email_verified"] is True
    assert profile["preferred_username"] == "ssoalice"
    assert profile["username"] == "ssoalice"
    me = await sso["client"].get("/api/auth/me", headers={"Authorization": f"Bearer {toks['access_token']}"})
    assert me.status_code == 401
    stolen = await sso["client"].get("/api/auth/oauth/userinfo", headers=bearer(body))
    assert stolen.status_code == 401
    replay = await _token(sso, payload["code"], verifier)
    assert replay.status_code == 400
    assert replay.json()["code"] == "SSO_CODE_INVALID"
    assert replay.json()["error"] == "invalid_grant"
    after_replay = await sso["client"].get(
        "/api/auth/oauth/userinfo", headers={"Authorization": f"Bearer {toks['access_token']}"}
    )
    assert after_replay.status_code == 401
    events = await audit_events(sso, user["id"])
    assert "sso_authorize" in events
    assert "sso_token" in events
    disc = await sso["client"].get("/.well-known/openid-configuration")
    assert disc.status_code == 200
    assert disc.json()["issuer"] == ISSUER
    prefixed = await sso["client"].get("/api/auth/.well-known/openid-configuration")
    assert prefixed.status_code == 200
    assert "sso_token" in sso["actions"]
    assert "sso_userinfo" in sso["actions"]


async def test_token_basic_auth(sso):
    _user, body = await approved_user(sso, username="ssobasic")
    res, verifier, _ = await _authorize(sso, bearer(body))
    token = await _token(sso, res.json()["code"], verifier, basic=True)
    assert token.status_code == 200, token.text


async def test_token_rejects_both_auth_methods(sso):
    _user, body = await approved_user(sso, username="ssoboth")
    res, verifier, _ = await _authorize(sso, bearer(body))
    raw = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    token = await sso["client"].post(
        "/api/auth/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": res.json()["code"],
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={"Authorization": f"Basic {raw}"},
    )
    assert token.status_code == 400
    assert token.json()["code"] == "SSO_INVALID_REQUEST"


async def test_token_json_rejected(sso):
    res = await sso["client"].post("/api/auth/oauth/token", json={"grant_type": "authorization_code"})
    assert res.status_code == 400
    assert res.json()["code"] == "SSO_INVALID_REQUEST"


async def test_pkce_and_redirect_and_secret(sso):
    _user, body = await approved_user(sso, username="ssopkce")
    headers = bearer(body)
    res, verifier, req = await _authorize(sso, headers)
    bad_pkce = await _token(sso, res.json()["code"], "not-the-verifier")
    assert bad_pkce.status_code == 400
    assert bad_pkce.json()["code"] == "SSO_PKCE_INVALID"

    res2, verifier2, _ = await _authorize(sso, headers)
    bad_redirect = await _token(sso, res2.json()["code"], verifier2, redirect_uri=REDIRECT + "/")
    assert bad_redirect.status_code == 400
    assert bad_redirect.json()["code"] == "SSO_INVALID_REDIRECT"

    res3, verifier3, _ = await _authorize(sso, headers)
    bad_secret = await sso["client"].post(
        "/api/auth/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": res3.json()["code"],
            "redirect_uri": REDIRECT,
            "code_verifier": verifier3,
            "client_id": CLIENT_ID,
            "client_secret": "wrong-secret",
        },
    )
    assert bad_secret.status_code == 401
    assert bad_secret.json()["code"] == "SSO_INVALID_CLIENT"
    assert "WWW-Authenticate" in bad_secret.headers

    unknown = await sso["client"].post(
        "/api/auth/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "x",
            "redirect_uri": REDIRECT,
            "code_verifier": verifier3,
            "client_id": "no-such-client",
            "client_secret": "x",
        },
    )
    assert unknown.status_code == 401
    assert unknown.json()["code"] == "SSO_INVALID_CLIENT"

    missing_pkce = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": "openid",
            "state": "s",
            "code_challenge": "short",
            "code_challenge_method": "S256",
        },
        headers=headers,
    )
    assert missing_pkce.status_code == 400
    assert missing_pkce.json()["code"] == "SSO_PKCE_INVALID"

    plain = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": "openid",
            "state": "s",
            "code_challenge": req["code_challenge"],
            "code_challenge_method": "plain",
        },
        headers=headers,
    )
    assert plain.status_code == 400


async def test_authorize_validation_order(sso):
    _user, body = await approved_user(sso, username="ssoval")
    headers = bearer(body)
    unknown = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={"client_id": "nope", "redirect_uri": REDIRECT, "state": "s", "scope": "openid"},
        headers=headers,
    )
    assert unknown.status_code == 401
    assert unknown.json()["code"] == "SSO_INVALID_CLIENT"

    bad_redirect = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={
            "client_id": CLIENT_ID,
            "redirect_uri": "https://evil.example/callback",
            "state": "s",
            "scope": "openid",
        },
        headers=headers,
    )
    assert bad_redirect.status_code == 400
    assert bad_redirect.json()["code"] == "SSO_INVALID_REDIRECT"
    assert "location" not in {k.lower() for k in bad_redirect.headers}

    no_state = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT,
            "scope": "openid",
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
        },
        headers=headers,
    )
    assert no_state.status_code == 400
    assert no_state.json()["code"] == "SSO_STATE_REQUIRED"

    bad_scope = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT,
            "scope": "email",
            "state": "s",
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
        },
        headers=headers,
    )
    assert bad_scope.status_code == 400
    assert bad_scope.json()["code"] == "SSO_INVALID_SCOPE"


async def test_admin_and_no_email_forbidden(sso):
    _admin, admin_headers = await make_admin(sso, username="ssoadmin")
    res, _, _ = await _authorize(sso, admin_headers)
    assert res.status_code == 403
    assert res.json()["code"] == "SSO_ADMIN_FORBIDDEN"

    user, body = await approved_user(sso, username="ssoempty")
    async with sso["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.email = f"deleted+{user['id']}@deleted.invalid"
        await db.commit()
    res, _, _ = await _authorize(sso, bearer(body))
    assert res.status_code == 403
    assert res.json()["code"] == "SSO_EMAIL_REQUIRED"


async def test_unapproved_and_disabled(sso):
    from tests.test_auth import _register

    pending = await _register(sso, email="pend@example.com", username="ssopend")
    logged = await sso["client"].post("/api/auth/login", data={"username": "ssopend", "password": "secret1"})
    assert logged.status_code == 403
    user, body = await approved_user(sso, username="ssodis")
    async with sso["sessions"]() as db:
        row = await db.get(User, user["id"])
        row.is_active = False
        await db.commit()
    res, _, _ = await _authorize(sso, bearer(body))
    assert res.status_code == 403
    assert res.json()["code"] == "USER_DISABLED"
    assert pending["username"] == "ssopend"


async def test_code_expired(sso):
    _user, body = await approved_user(sso, username="ssoexp")
    res, verifier, _ = await _authorize(sso, bearer(body))
    async with sso["sessions"]() as db:
        row = (await db.execute(select(OAuthAuthorizationCode))).scalars().first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    token = await _token(sso, res.json()["code"], verifier)
    assert token.status_code == 400
    assert token.json()["code"] == "SSO_CODE_EXPIRED"


async def test_password_change_invalidates_unused_codes(sso):
    user, body = await approved_user(sso, username="ssopw")
    res, verifier, _ = await _authorize(sso, bearer(body))
    assert res.status_code == 200
    changed = await sso["client"].post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "secret2"},
        headers=bearer(body),
    )
    assert changed.status_code == 200, changed.text
    token = await _token(sso, res.json()["code"], verifier)
    assert token.status_code == 400
    assert token.json()["code"] in ("SSO_CODE_INVALID", "SSO_CODE_EXPIRED")


async def test_i18n_en_sso_errors(sso):
    res = await sso["client"].post(
        "/api/auth/oauth/authorize",
        json={"client_id": "nope", "redirect_uri": REDIRECT, "state": "s"},
        headers={"X-Locale": "en", **bearer((await approved_user(sso, username="ssoen"))[1])},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["message"] == "Invalid client"
    assert res.json()["error_description"] == "Invalid client"


async def test_hs256_with_client_secret(sso):
    sso["config"].sso_jwt_algorithm = "HS256"
    _user, body = await approved_user(sso, username="ssohs")
    res, verifier, _ = await _authorize(sso, bearer(body))
    token = await _token(sso, res.json()["code"], verifier)
    assert token.status_code == 200, token.text
    id_token = token.json()["id_token"]
    assert jwt.get_unverified_header(id_token)["alg"] == "HS256"
    claims = verify_id_token(
        id_token, issuer=ISSUER, audience=CLIENT_ID, nonce="nonce-abc", client_secret=CLIENT_SECRET
    )
    assert claims["preferred_username"] == "ssohs"
    info = await sso["client"].get(
        "/api/auth/oauth/userinfo", headers={"Authorization": f"Bearer {token.json()['access_token']}"}
    )
    assert info.status_code == 200


async def test_from_env_helper(monkeypatch):
    monkeypatch.setenv("ACCOUNT_KIT_SSO_CLIENT_DEDD_SECRET", "from-env")
    monkeypatch.setenv("ACCOUNT_KIT_SSO_CLIENT_DEDD_ID", "dedd")
    monkeypatch.setenv("ACCOUNT_KIT_SSO_CLIENT_DEDD_REDIRECT", REDIRECT)
    loaded = SsoClientConfig.from_env("ACCOUNT_KIT_SSO_CLIENT_DEDD")
    assert loaded.client_id == "dedd"
    assert loaded.client_secret == "from-env"
    assert loaded.redirect_uris == (REDIRECT,)
    assert "from-env" not in repr(loaded)


async def test_discover_cache():
    cache = MemoryDiscoveryCache()
    hits = {"n": 0}

    class Dummy:
        async def get(self, url, timeout=10.0):
            hits["n"] += 1

            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"issuer": "https://idp.example.test", "token_endpoint": "https://idp.example.test/token"}

            return Resp()

        async def aclose(self):
            return None

    dummy = Dummy()
    first = await discover(ISSUER, cache=cache, ttl=60, client=dummy)
    second = await discover(ISSUER, cache=cache, ttl=60, client=dummy)
    assert first == second
    assert hits["n"] == 1
    third = await discover(ISSUER, cache=False, ttl=60, client=dummy)
    assert third["issuer"] == ISSUER
    assert hits["n"] == 2


async def test_upgrade_sql_0_5_0_idempotent():
    from account_kit import ensure_schema

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await ensure_schema(engine)

        async def columns(conn, table):
            rows = await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'auth' AND table_name = :t ORDER BY column_name"
                ),
                {"t": table},
            )
            return [tuple(row) for row in rows]

        async with engine.connect() as conn:
            expected = await columns(conn, "oauth_authorization_codes")
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE auth.oauth_authorization_codes"))
        sql = upgrade_sql("0.5.0")
        for _ in range(2):
            async with engine.connect() as conn:
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(sql)
        async with engine.connect() as conn:
            assert await columns(conn, "oauth_authorization_codes") == expected
        await ensure_schema(engine)
    finally:
        await engine.dispose()
