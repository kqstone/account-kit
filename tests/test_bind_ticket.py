"""0.7.0 stage 1B: bind tickets, verify_bind_target, WeChat bind-existing helper."""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import select

from account_kit import (
    BIND_TICKET_TTL_SECONDS,
    attach_mfa_challenge,
    consume_bind_ticket,
    discard_bind_mfa_challenge,
    issue_bind_ticket,
    load_bind_ticket,
    verify_bind_target,
)
from account_kit.bind_ticket import PURPOSE_SSO_BIND, ticket_hash
from account_kit.config import get_config
from account_kit.i18n import AccountError
from account_kit.models import BindTicket, User
from tests.helpers import approved_user, bearer, make_admin
from tests.test_auth import _register


class _Req:
    def __init__(self, ip="127.0.0.1"):
        self.client = type("client", (), {"host": ip})()
        self.headers = {}


def _claims(**extra):
    body = {
        "issuer": "https://idp.example.test/",
        "subject": "sub-1",
        "email": "ada@example.com",
        "name": "Ada",
        "email_verified": True,
    }
    body.update(extra)
    return body


async def _issue(db, **kwargs):
    claims = kwargs.pop("claims", None) or _claims()
    return await issue_bind_ticket(db, get_config(), claims=claims, **kwargs)


async def _enable_totp(client, headers, password="secret1"):
    setup = await client.post("/api/auth/2fa/setup", json={"password": password}, headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    totp = pyotp.TOTP(secret)
    enabled = await client.post("/api/auth/2fa/enable", json={"code": totp.at(time.time() - 30)}, headers=headers)
    assert enabled.status_code == 200, enabled.text
    return totp, enabled.json()["recovery_codes"]


async def test_issue_load_consume_once_then_replay(api):
    async with api["sessions"]() as db:
        raw, ttl = await _issue(db, ip="10.0.0.8")
        assert ttl == BIND_TICKET_TTL_SECONDS == 600
        assert raw and len(raw) >= 32
        ticket, claims = await load_bind_ticket(db, raw, config=get_config())
        assert ticket.status == "issued"
        assert ticket.ticket_hash == ticket_hash(raw)
        assert ticket.payload_cipher
        assert raw not in ticket.payload_cipher
        assert claims["iss"] == "https://idp.example.test"
        assert claims["sub"] == "sub-1"
        assert claims["email"] == "ada@example.com"
        assert claims["name"] == "Ada"
        assert claims["email_verified"] is True
        assert claims["jti"]
        assert "user_id" not in claims
        assert ticket.user_id is None
        consumed, again = await consume_bind_ticket(db, raw, config=get_config())
        assert consumed.status == "consumed"
        assert consumed.consumed_at is not None
        assert consumed.payload_cipher is None
        assert again["jti"] == claims["jti"]
        with pytest.raises(AccountError) as replay:
            await consume_bind_ticket(db, raw, config=get_config())
        assert replay.value.kit_code == "SSO_BIND_TICKET_CONSUMED"
        with pytest.raises(AccountError) as load_again:
            await load_bind_ticket(db, raw, config=get_config())
        assert load_again.value.kit_code == "SSO_BIND_TICKET_CONSUMED"
        row = (await db.execute(select(BindTicket))).scalars().one()
        assert row.ticket_hash == ticket_hash(raw)
        assert raw not in (row.payload_cipher or "")
        assert row.payload_cipher is None
        assert row.created_ip == "10.0.0.8"


async def test_expired_marks_and_clears_payload(api):
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        ticket.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        with pytest.raises(AccountError) as exc:
            await load_bind_ticket(db, raw, config=get_config())
        assert exc.value.kit_code == "SSO_BIND_TICKET_EXPIRED"
        row = (await db.execute(select(BindTicket))).scalars().one()
        assert row.status == "expired"
        assert row.payload_cipher is None
        with pytest.raises(AccountError) as again:
            await consume_bind_ticket(db, raw, config=get_config())
        assert again.value.kit_code == "SSO_BIND_TICKET_EXPIRED"


async def test_tampered_raw_and_cipher_invalid(api):
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
        with pytest.raises(AccountError) as missing:
            await load_bind_ticket(db, None, config=get_config())
        assert missing.value.kit_code == "SSO_BIND_TICKET_INVALID"
        with pytest.raises(AccountError) as empty:
            await load_bind_ticket(db, "", config=get_config())
        assert empty.value.kit_code == "SSO_BIND_TICKET_INVALID"
        with pytest.raises(AccountError) as bogus:
            await load_bind_ticket(db, raw + "x", config=get_config())
        assert bogus.value.kit_code == "SSO_BIND_TICKET_INVALID"
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        ticket.payload_cipher = "gAAAAABnot-a-real-fernet-token"
        await db.commit()
        with pytest.raises(AccountError) as cipher:
            await load_bind_ticket(db, raw, config=get_config())
        assert cipher.value.kit_code == "SSO_BIND_TICKET_INVALID"


async def test_purpose_and_user_id_anti_swap(api):
    user_a, _ = await approved_user(api, "ticketa", login=False)
    user_b, _ = await approved_user(api, "ticketb", login=False)
    async with api["sessions"]() as db:
        raw, _ = await _issue(db, purpose=PURPOSE_SSO_BIND, user_id=user_a["id"])
        with pytest.raises(AccountError) as purpose:
            await load_bind_ticket(db, raw, config=get_config(), purpose="bind")
        assert purpose.value.kit_code == "SSO_BIND_TICKET_INVALID"
        with pytest.raises(AccountError) as swap:
            await consume_bind_ticket(db, raw, config=get_config(), user_id=user_b["id"])
        assert swap.value.kit_code == "SSO_BIND_TICKET_INVALID"
        with pytest.raises(AccountError) as missing_uid:
            await consume_bind_ticket(db, raw, config=get_config())
        assert missing_uid.value.kit_code == "SSO_BIND_TICKET_INVALID"
        ticket, claims = await consume_bind_ticket(
            db, raw, config=get_config(), purpose=PURPOSE_SSO_BIND, user_id=user_a["id"]
        )
        assert ticket.status == "consumed"
        assert str(ticket.user_id) == str(user_a["id"])
        assert "user_id" not in claims


async def test_consume_respects_host_transaction(api):
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
    async with api["sessions"]() as db:
        await consume_bind_ticket(db, raw, config=get_config(), commit=False)
        await db.rollback()
    async with api["sessions"]() as db:
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        assert ticket.status == "issued"
        assert ticket.payload_cipher
        await consume_bind_ticket(db, raw, config=get_config(), commit=False)
        await db.commit()
    async with api["sessions"]() as db:
        with pytest.raises(AccountError) as exc:
            await load_bind_ticket(db, raw, config=get_config())
        assert exc.value.kit_code == "SSO_BIND_TICKET_CONSUMED"


async def test_concurrent_consume_once(api):
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)

    async def one():
        async with api["sessions"]() as db:
            try:
                await consume_bind_ticket(db, raw, config=get_config())
                return "ok"
            except AccountError as exc:
                return exc.kit_code

    results = await asyncio.gather(one(), one())
    assert set(results) == {"ok", "SSO_BIND_TICKET_CONSUMED"}
    async with api["sessions"]() as db:
        row = (await db.execute(select(BindTicket))).scalars().one()
        assert row.status == "consumed"
        assert row.payload_cipher is None


async def test_verify_bind_target_dummy_hash_lockout_admin_and_codes(api):
    api["config"].login_lockout_attempts = 3
    api["config"].login_lockout_seconds = 900
    req = _Req()
    for _ in range(2):
        with pytest.raises(AccountError) as missing:
            async with api["sessions"]() as db:
                await verify_bind_target(db, get_config(), req, username="ghost", password="nope")
        assert missing.value.kit_code == "INVALID_CREDENTIALS"
    with pytest.raises(AccountError) as locked:
        async with api["sessions"]() as db:
            await verify_bind_target(db, get_config(), req, username="ghost", password="nope")
    assert locked.value.kit_code == "ACCOUNT_LOCKED"

    pending = await _register(api, email="btpend@example.com", username="btpend")
    with pytest.raises(AccountError) as pend:
        async with api["sessions"]() as db:
            await verify_bind_target(db, get_config(), req, username="btpend", password="secret1")
    assert pend.value.kit_code == "ACCOUNT_PENDING"

    async with api["sessions"]() as db:
        row = await db.get(User, pending["id"])
        row.approval_status = "rejected"
        row.approval_reason = "材料不全"
        await db.commit()
    with pytest.raises(AccountError) as rej:
        async with api["sessions"]() as db:
            await verify_bind_target(db, get_config(), req, username="btpend", password="secret1")
    assert rej.value.kit_code == "ACCOUNT_REJECTED"
    assert rej.value.kit_params["reason"] == "材料不全"

    admin, _headers = await make_admin(api, "btadmin")
    with pytest.raises(AccountError) as forbidden:
        async with api["sessions"]() as db:
            await verify_bind_target(db, get_config(), req, username="btadmin", password="secret1")
    assert forbidden.value.kit_code == "SSO_ADMIN_FORBIDDEN"
    async with api["sessions"]() as db:
        allowed = await verify_bind_target(
            db, get_config(), req, username="btadmin", password="secret1", forbid_admin=False
        )
        assert allowed.is_admin is True
        assert str(allowed.id) == str(admin["id"])

    user, _ = await approved_user(api, "btemail", email="Bind.Me@example.com", login=False)
    async with api["sessions"]() as db:
        found = await verify_bind_target(db, get_config(), req, username="bind.me@example.com", password="secret1")
        assert str(found.id) == str(user["id"])


async def test_verify_bind_target_mfa_does_not_consume_ticket(api):
    user, tokens = await approved_user(api, "btmfa")
    totp, recovery = await _enable_totp(api["client"], bearer(tokens))
    req = _Req()
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
        with pytest.raises(AccountError) as mfa:
            await verify_bind_target(db, get_config(), req, username="btmfa", password="secret1")
        assert mfa.value.kit_code == "MFA_REQUIRED"
        assert mfa.value.kit_extra.get("challenge_token")
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        assert ticket.status == "issued"
        await attach_mfa_challenge(db, ticket, str(mfa.value.kit_extra["challenge_token"]))
        await db.refresh(ticket)
        assert ticket.status == "issued"
        assert ticket.payload_cipher
        assert ticket.mfa_challenge_hash
        passed = await verify_bind_target(
            db, get_config(), req, username="btmfa", password="secret1", code=totp.now()
        )
        assert str(passed.id) == str(user["id"])
        still, _ = await load_bind_ticket(db, raw, config=get_config())
        assert still.status == "issued"
        await consume_bind_ticket(db, raw, config=get_config())
    async with api["sessions"]() as db:
        inline = await verify_bind_target(
            db, get_config(), req, username="btmfa", password="secret1", recovery_code=recovery[0]
        )
        assert str(inline.id) == str(user["id"])


def test_wechat_bind_existing_reuses_helper_keep_admin_and_mfa_consume():
    from account_kit.wechat.service import bind_existing, complete_pending_wechat_bind

    src = inspect.getsource(bind_existing)
    assert "verify_bind_target" in src
    assert "forbid_admin=False" in src
    assert "complete_pending_wechat_bind" not in src
    assert "attach_mfa_challenge" not in src
    helper = inspect.getsource(complete_pending_wechat_bind)
    assert "bind_identity" in helper
    assert "consumed" in helper


async def test_stale_identity_map_does_not_revive_consumed_ticket(api):
    """Session A loads (issued in identity map); Session B consumes; Session A
    consume must see consumed, not replay the cached issued row/cipher."""
    async with api["sessions"]() as db_a:
        raw, _ = await _issue(db_a)
        ticket, _ = await load_bind_ticket(db_a, raw, config=get_config())
        assert ticket.status == "issued"
        assert ticket.payload_cipher
        async with api["sessions"]() as db_b:
            consumed, _ = await consume_bind_ticket(db_b, raw, config=get_config())
            assert consumed.status == "consumed"
            assert consumed.payload_cipher is None
        with pytest.raises(AccountError) as exc:
            await consume_bind_ticket(db_a, raw, config=get_config())
        assert exc.value.kit_code == "SSO_BIND_TICKET_CONSUMED"
        await db_a.rollback()
    async with api["sessions"]() as db:
        row = (await db.execute(select(BindTicket))).scalars().one()
        assert row.status == "consumed"
        assert row.payload_cipher is None


async def test_sso_bind_mfa_email_send_does_not_complete_via_login_2fa(api):
    """Email code for an SSO bind challenge must send, and POST /login/2fa must
    not take the WeChat complete branch or issue tokens; ticket stays issued."""
    api["config"].two_factor_email_enabled = True
    api["config"].wechat_enabled = True
    user, tokens = await approved_user(api, "btmail")
    totp, _recovery = await _enable_totp(api["client"], bearer(tokens))
    req = _Req()
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
        with pytest.raises(AccountError) as mfa:
            await verify_bind_target(db, get_config(), req, username="btmail", password="secret1")
        assert mfa.value.kit_code == "MFA_REQUIRED"
        challenge = str(mfa.value.kit_extra["challenge_token"])
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        await attach_mfa_challenge(db, ticket, challenge)
        assert ticket.status == "issued"
        assert ticket.mfa_challenge_hash
    sent = await api["client"].post(
        "/api/auth/login/2fa/email/send",
        json={"challenge_token": challenge, "language": "zh"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json().get("email")
    verify = await api["client"].post(
        "/api/auth/login/2fa",
        data={"challenge_token": challenge, "code": totp.now()},
    )
    assert verify.status_code == 400, verify.text
    assert verify.json()["code"] == "SSO_BIND_TICKET_INVALID"
    assert "access_token" not in (verify.json() or {})
    async with api["sessions"]() as db:
        still, _ = await load_bind_ticket(db, raw, config=get_config())
        assert still.status == "issued"
        assert still.payload_cipher
        passed = await verify_bind_target(
            db, get_config(), req, username="btmail", password="secret1", code=totp.now()
        )
        assert str(passed.id) == str(user["id"])
        await consume_bind_ticket(db, raw, config=get_config())


async def _expire_challenge(db, config, raw: str) -> None:
    from account_kit.models import TwoFactorChallenge
    from account_kit.two_factor.challenges import challenge_store, challenge_token_hash

    digest = challenge_token_hash(raw)
    if config.use_db_state():
        row = await db.get(TwoFactorChallenge, digest)
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        return
    item = challenge_store._items.get(digest)
    assert item is not None
    item.expires_at = time.monotonic() - 1


async def test_bind_mfa_challenge_passed_survives_conflict_then_discard(api):
    """2FA pass → simulated 409 → empty-code same challenge retry; discard blocks replay."""
    from account_kit.two_factor.challenges import challenge_token_hash, load_challenge

    user, tokens = await approved_user(api, "btch1")
    totp, _recovery = await _enable_totp(api["client"], bearer(tokens))
    req = _Req()
    async with api["sessions"]() as db:
        raw, _ = await _issue(db)
        with pytest.raises(AccountError) as mfa:
            await verify_bind_target(db, get_config(), req, username="btch1", password="secret1")
        assert mfa.value.kit_code == "MFA_REQUIRED"
        challenge = str(mfa.value.kit_extra["challenge_token"])
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        await attach_mfa_challenge(db, ticket, challenge)
        ticket, _ = await load_bind_ticket(db, raw, config=get_config())
        first = await verify_bind_target(
            db,
            get_config(),
            req,
            username="btch1",
            password="secret1",
            code=totp.now(),
            challenge_token=challenge,
            bind_ticket=ticket,
        )
        assert str(first.id) == str(user["id"])
        item = await load_challenge(db, get_config(), challenge)
        assert item is not None and item.passed is True
        still, _ = await load_bind_ticket(db, raw, config=get_config())
        assert still.status == "issued"
        retry = await verify_bind_target(
            db,
            get_config(),
            req,
            username="btch1",
            password="secret1",
            challenge_token=challenge,
            bind_ticket=ticket,
        )
        assert str(retry.id) == str(user["id"])
        consumed, _ = await consume_bind_ticket(db, raw, config=get_config(), commit=False)
        await db.commit()
        await discard_bind_mfa_challenge(db, consumed, challenge)
        assert consumed.mfa_challenge_hash is None
        assert await load_challenge(db, get_config(), challenge) is None

        raw2, _ = await _issue(db, claims=_claims(subject="sub-replay"))
        fresh, _ = await load_bind_ticket(db, raw2, config=get_config())
        fresh.mfa_challenge_hash = challenge_token_hash(challenge)
        await db.commit()
        with pytest.raises(AccountError) as replay:
            await verify_bind_target(
                db,
                get_config(),
                req,
                username="btch1",
                password="secret1",
                challenge_token=challenge,
                bind_ticket=fresh,
            )
        assert replay.value.kit_code == "MFA_CHALLENGE_INVALID"


async def test_bind_mfa_challenge_rejects_cross_user_ticket_purpose_expired(api):
    from account_kit.two_factor.challenges import load_challenge

    user_a, tokens_a = await approved_user(api, "btchA")
    totp_a, _ = await _enable_totp(api["client"], bearer(tokens_a))
    user_b, tokens_b = await approved_user(api, "btchB")
    totp_b, _ = await _enable_totp(api["client"], bearer(tokens_b))
    req = _Req()
    async with api["sessions"]() as db:
        raw_a, _ = await _issue(db, claims=_claims(subject="sub-a"))
        raw_b, _ = await _issue(db, claims=_claims(subject="sub-b"))
        with pytest.raises(AccountError) as mfa:
            await verify_bind_target(db, get_config(), req, username="btchA", password="secret1")
        challenge = str(mfa.value.kit_extra["challenge_token"])
        ticket_a, _ = await load_bind_ticket(db, raw_a, config=get_config())
        await attach_mfa_challenge(db, ticket_a, challenge)
        ticket_a, _ = await load_bind_ticket(db, raw_a, config=get_config())
        await verify_bind_target(
            db,
            get_config(),
            req,
            username="btchA",
            password="secret1",
            code=totp_a.now(),
            challenge_token=challenge,
            bind_ticket=ticket_a,
        )
        ticket_b, _ = await load_bind_ticket(db, raw_b, config=get_config())
        with pytest.raises(AccountError) as cross_ticket:
            await verify_bind_target(
                db,
                get_config(),
                req,
                username="btchA",
                password="secret1",
                challenge_token=challenge,
                bind_ticket=ticket_b,
            )
        assert cross_ticket.value.kit_code == "MFA_CHALLENGE_INVALID"
        with pytest.raises(AccountError) as cross_user:
            await verify_bind_target(
                db,
                get_config(),
                req,
                username="btchB",
                password="secret1",
                challenge_token=challenge,
                bind_ticket=ticket_a,
            )
        assert cross_user.value.kit_code == "MFA_CHALLENGE_INVALID"
        ticket_a.purpose = "bind"
        await db.commit()
        await db.refresh(ticket_a)
        with pytest.raises(AccountError) as purpose:
            await verify_bind_target(
                db,
                get_config(),
                req,
                username="btchA",
                password="secret1",
                challenge_token=challenge,
                bind_ticket=ticket_a,
                login_purpose="sso_bind",
            )
        assert purpose.value.kit_code == "MFA_CHALLENGE_INVALID"
        ticket_a.purpose = "sso_bind"
        await db.commit()
        await _expire_challenge(db, get_config(), challenge)
        with pytest.raises(AccountError) as expired_exc:
            await verify_bind_target(
                db,
                get_config(),
                req,
                username="btchA",
                password="secret1",
                challenge_token=challenge,
                bind_ticket=ticket_a,
            )
        assert expired_exc.value.kit_code == "MFA_CHALLENGE_INVALID"
        assert await load_challenge(db, get_config(), challenge) is None
        assert totp_b and user_b["id"]
