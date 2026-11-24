from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, TemplateNotFound

from account_kit.config import AccountKitConfig
from account_kit.i18n import email_lang_suffix, resolve_email_language, t

logger = logging.getLogger("account_kit.emailer")

_template_dir = os.path.join(os.path.dirname(__file__), "templates", "emails")

_DEFAULT_TEMPLATES = {
    "login_2fa": "two_factor_login_{lang}.html",
    "disable_2fa": "two_factor_disable_{lang}.html",
}

_NOTICE_TEMPLATES = {
    "approval_approved": "approval_approved_{lang}.html",
    "approval_rejected": "approval_rejected_{lang}.html",
    "admin_pending": "admin_pending_{lang}.html",
}


def _safe_template_name(name: str) -> Optional[str]:
    """Relative template names only; reject absolute paths and ``..`` segments."""
    cleaned = (name or "").replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/"):
        return None
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _jinja_env(config: AccountKitConfig) -> Environment:
    loaders = []
    override = (config.email_template_dir or "").strip()
    if override and os.path.isdir(override):
        loaders.append(FileSystemLoader(override))
    loaders.append(FileSystemLoader(_template_dir))
    loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]
    return Environment(loader=loader)


def _template_name(config: AccountKitConfig, purpose: str, lang: str) -> str:
    mapped = None
    if config.email_template_map:
        mapped = config.email_template_map.get(purpose)
    if mapped:
        safe = _safe_template_name(mapped)
        if safe:
            if "{lang}" in safe:
                return safe.format(lang=lang)
            return safe
    default = _DEFAULT_TEMPLATES.get(purpose, "verification_{lang}.html")
    return default.format(lang=lang)


def render_code_email(config: AccountKitConfig, purpose: str, code: str, language: str) -> tuple[str, str]:
    lang = email_lang_suffix(language)
    locale = "en" if lang == "en" else "zh-CN"
    action_key = f"EMAIL_ACTION_{purpose}"
    action = t(action_key, locale=locale)
    if action == action_key:
        action = purpose
    brand = config.brand_name
    params = {"brand": brand}
    if purpose in ("login_2fa", "disable_2fa"):
        subject = t(f"EMAIL_SUBJECT_{purpose}", params, locale=locale)
    else:
        subject = t("EMAIL_SUBJECT_generic", params, locale=locale)
    env = _jinja_env(config)
    name = _template_name(config, purpose, lang)
    try:
        tmpl = env.get_template(name)
    except TemplateNotFound:
        tmpl = env.get_template(f"verification_{lang}.html")
    body = tmpl.render(action=action, code=code, brand=brand)
    return subject, body


def smtp_configured(config: AccountKitConfig) -> bool:
    cfg = config.smtp
    return bool((cfg.host or "").strip() and (cfg.user or "").strip() and (cfg.password or "").strip())


def deliver_smtp(config: AccountKitConfig, to_email: str, subject: str, body: str) -> None:
    cfg = config.smtp
    if not smtp_configured(config):
        return
    msg = MIMEMultipart()
    sender = cfg.from_email or cfg.user
    msg["From"] = f"{config.brand_name} <{sender}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html", "utf-8"))
    if cfg.port == 465:
        server = smtplib.SMTP_SSL(cfg.host, cfg.port)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port)
        if cfg.tls:
            server.starttls()
    server.login(cfg.user, cfg.password)
    server.send_message(msg)
    server.quit()


async def send_code_email(
    config: AccountKitConfig, to_email: str, purpose: str, code: str, language: Optional[str] = None
) -> None:
    # Host mailers keep receiving "zh" / "en" (template suffix), not "zh-CN".
    lang = resolve_email_language(language)
    if config.mailer is not None:
        await config.mailer(to_email, purpose, code, lang)
        return
    subject, body = render_code_email(config, purpose, code, lang)
    deliver_smtp(config, to_email, subject, body)


def render_notice_email(
    config: AccountKitConfig, purpose: str, language: str, context: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    lang = email_lang_suffix(language)
    locale = "en" if lang == "en" else "zh-CN"
    ctx = dict(context or {})
    ctx.setdefault("brand", config.brand_name)
    ctx.setdefault("username", "")
    ctx.setdefault("email", "")
    ctx.setdefault("reason", "")
    ctx.setdefault("via", "")
    ctx.setdefault("public_base_url", config.public_base_url or "")
    subject = t(f"EMAIL_SUBJECT_{purpose}", {"brand": ctx["brand"]}, locale=locale)
    env = _jinja_env(config)
    mapped = None
    if config.email_template_map:
        mapped = config.email_template_map.get(purpose)
    name = None
    if mapped:
        safe = _safe_template_name(mapped)
        if safe:
            name = safe.format(lang=lang) if "{lang}" in safe else safe
    if not name:
        default = _NOTICE_TEMPLATES.get(purpose, "verification_{lang}.html")
        name = default.format(lang=lang)
    try:
        tmpl = env.get_template(name)
    except TemplateNotFound:
        tmpl = env.get_template(f"verification_{lang}.html")
    body = tmpl.render(**ctx)
    return subject, body


async def send_notice_email(
    config: AccountKitConfig,
    to_email: str,
    purpose: str,
    *,
    language: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Approval / admin-pending notices. Skip when SMTP and notice_mailer are unset.
    Failures are logged as warnings and never raised to the caller."""
    if not getattr(config, "approval_emails_enabled", True):
        return
    address = (to_email or "").strip()
    if not address:
        return
    lang = resolve_email_language(language)
    ctx = dict(context or {})
    if config.notice_mailer is not None:
        try:
            await config.notice_mailer(address, purpose, lang, ctx)
        except Exception:
            logger.warning("account-kit notice mailer failed (%s -> %s)", purpose, address, exc_info=True)
        return
    if not smtp_configured(config):
        return
    try:
        subject, body = render_notice_email(config, purpose, lang, ctx)
        deliver_smtp(config, address, subject, body)
    except Exception:
        logger.warning("account-kit approval email failed (%s -> %s)", purpose, address, exc_info=True)
