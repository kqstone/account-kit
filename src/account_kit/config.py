from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""
    tls: bool = True


# to, purpose, code, language
Mailer = Callable[[str, str, str, str], Awaitable[None]]
UserHook = Callable[[AsyncSession, object], Awaitable[None]]


@dataclass
class AccountKitConfig:
    """Runtime settings supplied by the host app. Nothing here is a quota."""

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    # stateless | single_device
    session_mode: str = "stateless"
    session_active_hours: int = 12
    require_approval: bool = False
    email_domain_restriction: bool = False
    allowed_email_domains: Tuple[str, ...] = ()
    brand_name: str = "Account"
    password_min_length: int = 6
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    # HMAC material for email codes and recovery codes. Falls back to jwt_secret.
    secret_key: str = ""
    # Fernet material for TOTP secrets. Falls back to secret_key, then jwt_secret.
    file_encryption_key: str = ""
    two_factor_enabled: bool = True
    role_change_enabled: bool = False
    trusted_device_days: int = 30
    forbid_admin_like_usernames: bool = False
    reserved_usernames: Tuple[str, ...] = ()
    api_prefix: str = "/api/auth"
    admin_prefix: str = "/api/admin/account"
    mailer: Optional[Mailer] = None
    on_registered: Optional[UserHook] = None
    on_login: Optional[UserHook] = None
    on_password_changed: Optional[UserHook] = None
    on_deleted: Optional[UserHook] = None

    def code_secret(self) -> str:
        return self.secret_key or self.jwt_secret

    def encryption_material(self) -> str:
        return self.file_encryption_key or self.secret_key or self.jwt_secret


_config: Optional[AccountKitConfig] = None


def set_config(config: AccountKitConfig) -> None:
    global _config
    _config = config


def get_config() -> AccountKitConfig:
    if _config is None:
        raise RuntimeError("account-kit is not configured")
    return _config
