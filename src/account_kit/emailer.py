from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, TemplateNotFound

from account_kit.config import AccountKitConfig

_template_dir = os.path.join(os.path.dirname(__file__), "templates", "emails")

_ACTIONS = {
    "zh": {
        "register": "注册账户",
        "reset_password": "重置密码",
        "change_password": "修改密码",
        "login_2fa": "登录验证",
        "disable_2fa": "关闭两步验证",
        "change_email": "修改账号邮箱",
        "delete_account": "注销账号",
    },
    "en": {
        "register": "register",
        "reset_password": "reset your password",
        "change_password": "change your password",
        "login_2fa": "sign in",
        "disable_2fa": "turn off two-factor authentication",
        "change_email": "change your account email",
        "delete_account": "delete your account",
    },
}

_DEFAULT_TEMPLATES = {
    "login_2fa": "two_factor_login_{lang}.html",
    "disable_2fa": "two_factor_disable_{lang}.html",
}

_SUBJECTS = {
    ("login_2fa", "zh"): "【{brand}】登录验证码",
    ("login_2fa", "en"): "[{brand}] Your sign-in verification code",
    ("disable_2fa", "zh"): "【{brand}】关闭两步验证验证码",
    ("disable_2fa", "en"): "[{brand}] Code to turn off two-step verification",
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
    lang = language if language in ("zh", "en") else "zh"
    action = _ACTIONS[lang].get(purpose, purpose)
    brand = config.brand_name
    subject_tmpl = _SUBJECTS.get((purpose, lang))
    if subject_tmpl:
        subject = subject_tmpl.format(brand=brand)
    elif lang == "zh":
        subject = f"【{brand}】验证码"
    else:
        subject = f"[{brand}] Verification code"
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


async def send_code_email(config: AccountKitConfig, to_email: str, purpose: str, code: str, language: str = "zh") -> None:
    if config.mailer is not None:
        await config.mailer(to_email, purpose, code, language)
        return
    subject, body = render_code_email(config, purpose, code, language)
    deliver_smtp(config, to_email, subject, body)
