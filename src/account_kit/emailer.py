from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader

from account_kit.config import AccountKitConfig

_template_dir = os.path.join(os.path.dirname(__file__), "templates", "emails")
_jinja = Environment(loader=FileSystemLoader(_template_dir))

_ACTIONS = {
    "zh": {
        "register": "注册账户",
        "reset_password": "重置密码",
        "change_password": "修改密码",
        "login_2fa": "登录验证",
        "disable_2fa": "关闭两步验证",
    },
    "en": {
        "register": "register",
        "reset_password": "reset your password",
        "change_password": "change your password",
        "login_2fa": "sign in",
        "disable_2fa": "turn off two-factor authentication",
    },
}


def render_code_email(config: AccountKitConfig, purpose: str, code: str, language: str) -> tuple[str, str]:
    lang = language if language in ("zh", "en") else "zh"
    action = _ACTIONS[lang].get(purpose, purpose)
    brand = config.brand_name
    if lang == "zh":
        subject = f"【{brand}】验证码"
    else:
        subject = f"[{brand}] Verification code"
    body = _jinja.get_template(f"verification_{lang}.html").render(action=action, code=code, brand=brand)
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
