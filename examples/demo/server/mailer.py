"""Demo mailer: always print + keep an in-memory outbox; optional SMTP."""

from __future__ import annotations

import asyncio
import smtplib
from collections import deque
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Deque, Dict, List, Optional


class Outbox:
    def __init__(self, maxlen: int = 50) -> None:
        self._items: Deque[Dict[str, Any]] = deque(maxlen=maxlen)

    def add(self, to: str, purpose: str, code: str, language: str) -> Dict[str, Any]:
        item = {
            "to": to,
            "purpose": purpose,
            "code": code,
            "language": language or "zh",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._items.appendleft(item)
        print(
            f"[demo mail] to={to} purpose={purpose} code={code} language={item['language']}",
            flush=True,
        )
        return item

    def list(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def latest(self, to: Optional[str] = None, purpose: Optional[str] = None) -> Optional[Dict[str, Any]]:
        email = (to or "").strip().lower()
        for item in self._items:
            if email and item["to"].lower() != email:
                continue
            if purpose and item["purpose"] != purpose:
                continue
            return item
        return None


def _send_smtp(smtp: Dict[str, Any], to_email: str, subject: str, body: str, brand: str) -> None:
    host = (smtp.get("host") or "").strip()
    if not host:
        return
    port = int(smtp.get("port") or 587)
    user = smtp.get("user") or ""
    password = smtp.get("password") or ""
    from_email = smtp.get("from_email") or user or "demo@localhost"
    tls = bool(smtp.get("tls", True))
    msg = MIMEMultipart()
    msg["From"] = f"{brand} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html", "utf-8"))
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=10)
    else:
        server = smtplib.SMTP(host, port, timeout=10)
        if tls:
            server.starttls()
    if user and password:
        server.login(user, password)
    server.send_message(msg)
    server.quit()


def make_mailer(outbox: Outbox, smtp_provider, brand_provider):
    """Return an account-kit ``mailer`` callback.

    ``smtp_provider`` / ``brand_provider`` are zero-arg callables so the mailer
    can be built before init and still see the saved config later.
    """

    async def mailer(to: str, purpose: str, code: str, language: str) -> None:
        outbox.add(to, purpose, code, language)
        smtp = smtp_provider() or {}
        if not smtp.get("host"):
            return
        try:
            from account_kit.config import get_config
            from account_kit.emailer import render_code_email

            subject, body = render_code_email(get_config(), purpose, code, language or "zh")
        except Exception:
            brand = brand_provider()
            subject = f"【{brand}】验证码"
            body = f"<p>{purpose}: <b>{code}</b></p>"
        brand = brand_provider()
        try:
            await asyncio.to_thread(_send_smtp, smtp, to, subject, body, brand)
        except Exception as exc:
            print(f"[demo mail] smtp failed: {exc}", flush=True)

    return mailer
