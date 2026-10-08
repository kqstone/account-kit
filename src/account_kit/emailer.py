from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, TemplateNotFound

from account_kit.config import AccountKitConfig
from account_kit.i18n import email_lang_suffix, resolve_email_language, t

_template_dir = os.path.join(os.path.dirname(__file__), "templates", "emails")

_DEFAULT_TEMPLATES = {
    "login_2fa": "two_factor_login_{lang}.html",
    "disable_2fa": "two_factor_disable_{lang}.html",
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


def deliver_smtp(config: AccountKitConfig, to_email: str, subject: str, body: str) -> None:
    cfg = config.smtp
    if not cfg.user or not cfg.password:
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
