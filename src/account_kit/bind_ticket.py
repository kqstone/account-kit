"""SSO bind tickets: high-entropy one-shot tokens with Fernet claims.

The browser sees the opaque ``raw`` once. The database stores only
``sha256("sso-bind-ticket:" + raw)``. Payload is Fernet JSON (IdP iss/sub/email/name);
plaintext IdP identifiers never sit in a JWT. Consume uses ``SELECT FOR UPDATE``
so two workers cannot both succeed. Pass ``commit=False`` so the host can write
``sso_links`` and consume the ticket in one transaction.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from account_kit.config import AccountKitConfig, get_config
from account_kit.crypto import fernet_for
from account_kit.i18n import account_error
from account_kit.models import BindTicket

BIND_TICKET_TTL_SECONDS = 600
PURPOSE_SSO_BIND = "sso_bind"
STATUS_ISSUED = "issued"
STATUS_CONSUMED = "consumed"
STATUS_EXPIRED = "expired"


def ticket_hash(raw: str) -> str:
    return hashlib.sha256(("sso-bind-ticket:" + (raw or "")).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _ttl_seconds(config: AccountKitConfig) -> int:
    try:
        value = int(config.sso_bind_ticket_ttl_seconds or BIND_TICKET_TTL_SECONDS)
    except (TypeError, ValueError):
        value = BIND_TICKET_TTL_SECONDS
    return max(1, value)


def encrypt_payload(config: AccountKitConfig, payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return fernet_for(config.encryption_material()).encrypt(raw).decode("ascii")


def decrypt_payload(config: AccountKitConfig, cipher: Optional[str]) -> Dict[str, Any]:
    if not cipher:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    try:
        raw = fernet_for(config.encryption_material()).decrypt(cipher.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError, ValueError, TypeError):
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    if not isinstance(data, dict):
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    return data


def _as_uuid(value) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _claims_from(claims: Dict[str, Any]) -> Dict[str, Any]:
    issuer = str(claims.get("issuer") or "").strip().rstrip("/")
    subject = str(claims.get("subject") or "").strip()
    if not issuer or not subject:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    return {
        "iss": issuer,
        "sub": subject,
        "email": str(claims.get("email") or ""),
        "name": str(claims.get("name") or ""),
        "email_verified": bool(claims.get("email_verified")),
        "jti": uuid4().hex,
    }


async def issue_bind_ticket(
    db: AsyncSession,
    config: Optional[AccountKitConfig] = None,
    *,
    purpose: str = PURPOSE_SSO_BIND,
    claims: Dict[str, Any],
    ip: str = "",
    user_id=None,
    commit: bool = True,
) -> Tuple[str, int]:
    """Issue a 600s (default) one-shot ticket. Returns ``(raw, ttl_seconds)``.

    ``user_id`` is for logged-in personal-center bind tickets (anti-swap).
    Login/callback tickets leave it null; payload never contains a local user id.
    """
    cfg = config if config is not None else get_config()
    ttl = _ttl_seconds(cfg)
    raw = secrets.token_urlsafe(32)
    payload = _claims_from(claims or {})
    row = BindTicket(
        ticket_hash=ticket_hash(raw),
        purpose=(purpose or PURPOSE_SSO_BIND).strip() or PURPOSE_SSO_BIND,
        status=STATUS_ISSUED,
        user_id=_as_uuid(user_id),
        payload_cipher=encrypt_payload(cfg, payload),
        expires_at=_now() + timedelta(seconds=ttl),
        created_ip=(ip or "")[:64] or None,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return raw, ttl


async def load_bind_ticket(
    db: AsyncSession,
    raw: Optional[str],
    *,
    config: Optional[AccountKitConfig] = None,
    consume: bool = False,
    purpose: Optional[str] = None,
    user_id=None,
    commit: bool = True,
) -> Tuple[BindTicket, Dict[str, Any]]:
    """Hash-lookup. Expired → ``SSO_BIND_TICKET_EXPIRED`` (row marked expired, payload GC'd).
    Replay → ``SSO_BIND_TICKET_CONSUMED``. Tamper / unknown → ``SSO_BIND_TICKET_INVALID``.

    ``consume=True`` takes ``SELECT FOR UPDATE``, writes ``consumed_at`` and clears
    ``payload_cipher``. Pass ``commit=False`` for host-transaction atomicity.
    ``purpose`` / ``user_id`` bind the ticket so a logged-in bind ticket cannot be
    swapped onto another account.
    """
    cfg = config if config is not None else get_config()
    if not raw or not isinstance(raw, str) or len(raw) > 256:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    digest = ticket_hash(raw.strip())
    stmt = select(BindTicket).where(BindTicket.ticket_hash == digest)
    # Always refresh identity-map rows. A prior load in this Session plus
    # another Session consuming the ticket would otherwise return the stale
    # ``issued`` instance (and its leftover payload_cipher) even after FOR UPDATE.
    stmt = stmt.execution_options(populate_existing=True)
    if consume:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    ticket = result.scalars().first()
    if ticket is None:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")

    wanted_purpose = (purpose or "").strip()
    if wanted_purpose and ticket.purpose != wanted_purpose:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    expected_user = _as_uuid(user_id)
    if expected_user is not None and ticket.user_id != expected_user:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")
    if consume and ticket.user_id is not None and expected_user is None:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")

    if ticket.status == STATUS_CONSUMED:
        raise account_error(400, "SSO_BIND_TICKET_CONSUMED")

    now = _now()
    expired = ticket.status == STATUS_EXPIRED or (
        _aware(ticket.expires_at) is not None and _aware(ticket.expires_at) <= now
    )
    if expired:
        ticket.status = STATUS_EXPIRED
        ticket.payload_cipher = None
        if commit:
            await db.commit()
            await db.refresh(ticket)
        raise account_error(400, "SSO_BIND_TICKET_EXPIRED")

    if ticket.status != STATUS_ISSUED:
        raise account_error(400, "SSO_BIND_TICKET_INVALID")

    claims = decrypt_payload(cfg, ticket.payload_cipher)
    if consume:
        ticket.status = STATUS_CONSUMED
        ticket.consumed_at = now
        ticket.payload_cipher = None
        if commit:
            await db.commit()
            await db.refresh(ticket)
    return ticket, claims


async def consume_bind_ticket(
    db: AsyncSession,
    raw: Optional[str],
    *,
    config: Optional[AccountKitConfig] = None,
    purpose: Optional[str] = None,
    user_id=None,
    commit: bool = True,
) -> Tuple[BindTicket, Dict[str, Any]]:
    """Single-use consume. Same lock / GC / anti-swap rules as ``load_bind_ticket``."""
    return await load_bind_ticket(
        db,
        raw,
        config=config,
        consume=True,
        purpose=purpose,
        user_id=user_id,
        commit=commit,
    )


async def attach_mfa_challenge(
    db: AsyncSession,
    ticket: BindTicket,
    challenge_token: str,
    *,
    config: Optional[AccountKitConfig] = None,
    commit: bool = True,
) -> None:
    """Link a 2FA challenge to an issued ticket. Does not consume the ticket.

    Stamps the live challenge with this ticket's hash and purpose so reuse
    cannot cross tickets. Association is the server-side ticket row, not a
    client-reported jti.
    """
    from account_kit.two_factor.challenges import challenge_token_hash, load_challenge, save_challenge

    cfg = config if config is not None else get_config()
    raw = (challenge_token or "").strip()
    if not raw:
        ticket.mfa_challenge_hash = None
    else:
        item = await load_challenge(db, cfg, raw)
        if item is None:
            raise account_error(401, "MFA_CHALLENGE_INVALID", as_dict=True)
        item.ticket_hash = ticket.ticket_hash
        item.purpose = ticket.purpose
        await save_challenge(db, cfg, raw, item)
        ticket.mfa_challenge_hash = challenge_token_hash(raw)
    if commit:
        await db.commit()
        await db.refresh(ticket)


async def find_bind_ticket_by_mfa(db: AsyncSession, challenge_token: str) -> Optional[BindTicket]:
    """Return the issued SSO bind ticket attached to this login-2FA challenge, if any."""
    from account_kit.two_factor.challenges import challenge_token_hash

    digest = challenge_token_hash(challenge_token or "")
    if not digest:
        return None
    stmt = (
        select(BindTicket)
        .where(BindTicket.mfa_challenge_hash == digest)
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalars().first()


async def discard_bind_mfa_challenge(
    db: AsyncSession,
    ticket: BindTicket,
    challenge_token: str,
    *,
    config: Optional[AccountKitConfig] = None,
    commit: bool = True,
) -> None:
    """Drop the 2FA challenge after the host has bound the identity and issued tokens.

    Safe to call if the challenge is already gone. Clears ``ticket.mfa_challenge_hash``.
    """
    from account_kit.two_factor.challenges import discard_challenge

    cfg = config if config is not None else get_config()
    await discard_challenge(db, cfg, challenge_token)
    ticket.mfa_challenge_hash = None
    if commit:
        await db.commit()


__all__ = [
    "BIND_TICKET_TTL_SECONDS",
    "PURPOSE_SSO_BIND",
    "STATUS_CONSUMED",
    "STATUS_EXPIRED",
    "STATUS_ISSUED",
    "attach_mfa_challenge",
    "consume_bind_ticket",
    "decrypt_payload",
    "discard_bind_mfa_challenge",
    "encrypt_payload",
    "find_bind_ticket_by_mfa",
    "issue_bind_ticket",
    "load_bind_ticket",
    "ticket_hash",
]
