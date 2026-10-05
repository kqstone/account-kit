from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Union
from uuid import UUID

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
UserHook = Callable[..., Awaitable[None]]
# request, username
BeforeLogin = Callable[[object, str], Awaitable[None]]
# request
BeforeRegister = Callable[[object], Awaitable[None]]
# request, user: runs before each 2FA verification / email code send (e.g. rate limits)
BeforeTwoFactor = Callable[[object, object], Awaitable[None]]
# captcha_id, captcha_code -> valid (sync or async); should consume the captcha
CaptchaVerifier = Callable[[str, str], Union[bool, Awaitable[bool]]]
# request -> client IP (e.g. honour X-Forwarded-For behind a trusted proxy)
ClientIp = Callable[[object], str]
# user_id, raw bytes, content_type, filename -> storage key written to User.avatar_path
AvatarSave = Callable[[UUID, bytes, Optional[str], Optional[str]], Awaitable[str]]
# previous storage key
AvatarDelete = Callable[[Optional[str]], Awaitable[None]]
# storage key -> (file_like_or_path_or_bytes, media_type)
AvatarOpen = Callable[[str], Awaitable[Tuple[Any, str]]]
EmailTemplateMap = Dict[str, str]


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
    # Login 2FA challenge lifetime and wrong-code limit per challenge. Read on each
    # request, so a host may update them at runtime (e.g. from admin settings).
    two_factor_challenge_ttl_seconds: int = 300
    two_factor_max_attempts: int = 5
    # Email code as an alternative second factor: login fallback
    # (POST /login/2fa/email/send + ``email_code``) and disabling 2FA in settings
    # (POST /2fa/disable/email-code + ``email_code``). Off by default.
    two_factor_email_enabled: bool = False
    # Image captcha on POST /login after repeated failures. Enabled when a verifier
    # is set; the host serves the captcha itself (e.g. GET {api_prefix}/captcha).
    captcha_verifier: Optional[CaptchaVerifier] = None
    captcha_fail_threshold: int = 3
    captcha_fail_window_seconds: int = 900
    client_ip: Optional[ClientIp] = None
    forbid_admin_like_usernames: bool = False
    reserved_usernames: Tuple[str, ...] = ()
    api_prefix: str = "/api/auth"
    admin_prefix: str = "/api/admin/account"
    # Host directory of Jinja templates; same filenames as the package defaults
    # are tried first, then account-kit's bundled templates.
    email_template_dir: Optional[str] = None
    # purpose -> template filename (relative, no ``..``). ``{lang}`` is expanded.
    email_template_map: Optional[EmailTemplateMap] = None
    # POST /change-password: default matches dedd (old/new password, no email code).
    # PATCH /me still requires an email code when changing the password.
    change_password_require_email_code: bool = False
    avatar_enabled: bool = False
    avatar_save: Optional[AvatarSave] = None
    avatar_delete: Optional[AvatarDelete] = None
    avatar_open: Optional[AvatarOpen] = None
    mailer: Optional[Mailer] = None
    before_login: Optional[BeforeLogin] = None
    before_register: Optional[BeforeRegister] = None
    before_two_factor: Optional[BeforeTwoFactor] = None
    on_registered: Optional[UserHook] = None
    on_login: Optional[UserHook] = None
    on_password_changed: Optional[UserHook] = None
    on_deleted: Optional[UserHook] = None

    def challenge_ttl(self) -> int:
        return max(30, int(self.two_factor_challenge_ttl_seconds or 300))

    def challenge_max_attempts(self) -> int:
        return max(1, int(self.two_factor_max_attempts or 5))

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
