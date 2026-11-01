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
# request, email, purpose: runs before every verification-code email (send-code,
# 2FA email codes, change-email, delete-account). Raise HTTPException to refuse.
BeforeSendCode = Callable[[object, str, str], Awaitable[None]]
# request, action, info: generic hook before sensitive kit actions. ``action`` is one
# of send_code, verify_code, register, reset_password, change_password, change_email,
# refresh, logout, delete_account, captcha, wechat_start, wechat_confirm, wechat_bind,
# wechat_unbind, wechat_register, sso_authorize, sso_token, sso_userinfo.
# ``info`` is a small dict (email, purpose, user).
BeforeAction = Callable[[object, str, Dict[str, Any]], Awaitable[None]]
# js_code -> {openid, unionid?}. session_key must be dropped by the callable.
WechatCode2Session = Callable[[str], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]
# scene, page, env_version, check_path, width -> PNG/JPEG bytes
WechatGetWxaCode = Callable[..., Union[bytes, Awaitable[bytes]]]
# db, event, user_id, meta: called after each audit row is written (or instead, when
# ``audit_log_enabled`` is False). Never raises into the request.
AuditHook = Callable[..., Awaitable[None]]
# request -> locale tag (e.g. cookie / JWT / host i18n). Return None to fall through.
LocaleResolver = Callable[[object], Optional[str]]


@dataclass
class SsoClientConfig:
    """One OIDC relying party. ``client_secret`` is server-side only (from env)."""

    client_id: str
    client_secret: str
    redirect_uris: Tuple[str, ...] = ()
    name: str = ""

    def __repr__(self) -> str:
        return (
            f"SsoClientConfig(client_id={self.client_id!r}, name={self.name!r}, "
            f"redirect_uris={self.redirect_uris!r})"
        )

    @classmethod
    def from_env(
        cls,
        prefix: str,
        *,
        client_id: str = "",
        redirect_uris: Optional[Tuple[str, ...]] = None,
        name: str = "",
    ) -> "SsoClientConfig":
        """Load secret (and optional id/redirect/name) from ``{prefix}_SECRET`` etc.

        Example prefix ``ACCOUNT_KIT_SSO_CLIENT_DEDD`` reads
        ``ACCOUNT_KIT_SSO_CLIENT_DEDD_SECRET``.
        """
        import os

        p = (prefix or "").rstrip("_")
        cid = (client_id or os.environ.get(f"{p}_ID") or os.environ.get(f"{p}_CLIENT_ID") or "").strip()
        secret = os.environ.get(f"{p}_SECRET") or os.environ.get(f"{p}_CLIENT_SECRET") or ""
        raw_redirect = os.environ.get(f"{p}_REDIRECT") or os.environ.get(f"{p}_REDIRECT_URI") or ""
        uris = (
            redirect_uris
            if redirect_uris is not None
            else tuple(u.strip() for u in raw_redirect.split(",") if u.strip())
        )
        nm = name or os.environ.get(f"{p}_NAME") or ""
        return cls(client_id=cid, client_secret=secret, redirect_uris=uris, name=nm)


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
    # POST /change-password: by default only old/new password, no email code.
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

    # --- 0.2.2 ----------------------------------------------------------------
    # Where short-lived security state lives: login-failure counters, rate-limit
    # counters, 2FA login challenges and built-in captchas. ``db`` (default) uses
    # tables in schema ``auth`` and works across processes/instances; ``memory``
    # keeps the pre-0.2.2 per-process behaviour.
    state_backend: str = "db"
    # Verification codes: wrong attempts per email+purpose before every outstanding
    # code for that email+purpose is invalidated (the user must request a new one).
    verify_code_max_attempts: int = 5
    # Send limits for emailed codes (send-code, 2FA email, change-email, delete-account).
    # 0 disables a limit.
    send_code_rate_limit_ip: int = 10
    send_code_rate_limit_email: int = 5
    send_code_rate_window_seconds: int = 3600
    # Optional per-IP limits on other unauthenticated endpoints (0 = off; hosts that
    # already throttle in before_login / before_register keep doing so).
    reset_password_rate_limit_ip: int = 10
    reset_password_rate_window_seconds: int = 3600
    register_rate_limit_ip: int = 0
    register_rate_window_seconds: int = 3600
    login_rate_limit_ip: int = 0
    login_rate_limit_user: int = 0
    login_rate_window_seconds: int = 60
    before_send_code: Optional[BeforeSendCode] = None
    before_action: Optional[BeforeAction] = None
    # Email change: PATCH /me ``email`` handling.
    #   verify (default): needs ``email_code`` sent by POST /me/email/send-code to the
    #                     new address (and ``current_password`` when
    #                     change_email_require_password is on);
    #   reject:          PATCH /me refuses email changes, use POST /me/email;
    #   direct:          pre-0.2.2 behaviour (no verification). Not recommended.
    profile_email_change: str = "verify"
    change_email_require_password: bool = True
    # Refresh tokens (opt-in). Login and /login/2fa add ``refresh_token`` and
    # ``refresh_expires_in``; POST /refresh rotates them with reuse detection.
    refresh_token_enabled: bool = False
    refresh_token_expire_days: int = 30
    # POST {api_prefix}{logout_path}. Lenient: an expired/replaced access token
    # still returns 200 and never clears somebody else's newer session.
    logout_enabled: bool = True
    logout_path: str = "/logout"
    on_logout: Optional[UserHook] = None
    # Self-service deletion: POST /me/delete (and DELETE /me). Off by default.
    self_delete_enabled: bool = False
    # hard: delete the row (pre-0.2.2 admin behaviour). soft: deactivate, anonymise
    # username/email/profile and revoke every credential, keeping the row for FKs.
    # Applies to admin DELETE /users/{id} and self-delete alike.
    user_delete_mode: str = "hard"
    # Audit log (auth.auth_audit_logs). GET {admin_prefix}/audit-logs lists it.
    audit_log_enabled: bool = True
    on_audit: Optional[AuditHook] = None
    # Built-in image captcha (needs ``pip install account-kit[captcha]``). When on,
    # kit serves GET {api_prefix}/captcha and verifies it itself unless a
    # ``captcha_verifier`` is also given (host-provided captcha keeps working).
    captcha_builtin: bool = False
    captcha_ttl_seconds: int = 300
    captcha_length: int = 4

    # --- admin security -------------------------------------------------------
    # Per-account login lockout. 0 attempts = off. Admin uses the admin_* pair
    # even when the global lockout is off.
    login_lockout_attempts: int = 0
    login_lockout_seconds: int = 900
    admin_login_lockout_attempts: int = 5
    admin_login_lockout_seconds: int = 900
    admin_login_rate_limit_user: int = 0
    admin_login_captcha_always: bool = False
    admin_require_2fa: bool = False
    admin_ip_allowlist: Tuple[str, ...] = ()
    # None = inherit access_token_expire_minutes.
    admin_access_token_expire_minutes: Optional[int] = None
    admin_refresh_disabled: bool = False
    # None = inherit password_min_length.
    admin_password_min_length: Optional[int] = None
    admin_setup_require_password: bool = True
    audit_admin_login: bool = True

    # --- i18n (0.3.0) ---------------------------------------------------------
    default_locale: str = "zh-CN"
    supported_locales: Tuple[str, ...] = ("zh-CN", "en")
    locale_header: str = "X-Locale"
    locale_query: str = "locale"
    negotiate_accept_language: bool = False
    locale_resolver: Optional[LocaleResolver] = None
    # locale -> code -> text, deep-merged over the built-in catalog.
    messages_override: Optional[Dict[str, Dict[str, str]]] = None
    localize_validation: bool = False

    # --- wechat Mini Program QR login (0.4.0) ---------------------------------
    # Off by default. Routes are registered only when ``wechat_enabled`` is True.
    wechat_enabled: bool = False
    wechat_app_id: str = ""
    # Server-side only. Never returned by any GET endpoint.
    wechat_app_secret: str = ""
    wechat_qr_ttl_seconds: int = 120
    wechat_qr_page: str = "pages/login/confirm"
    wechat_bind_page: str = "pages/login/confirm"
    wechat_env_version: str = "release"
    wechat_check_path: bool = True
    wechat_login_rate_limit_ip: int = 20
    wechat_satisfies_mfa: bool = True
    wechat_allow_register: bool = True
    wechat_code2session: Optional[WechatCode2Session] = None
    wechat_get_wxacode: Optional[WechatGetWxaCode] = None

    # --- OIDC IdP (0.5.0) ----------------------------------------------------
    # Off by default. Routes are registered only when ``sso_idp_enabled`` is True.
    # Per-request: False after mount → 403 SSO_DISABLED (hot-off). Turning on at
    # runtime without remounting does not add routes.
    sso_idp_enabled: bool = False
    sso_issuer: str = ""
    # RS256 (default): PEM private key; JWKS publishes the public key + kid.
    # HS256: each client's client_secret signs tokens. Never falls back to jwt_secret.
    sso_jwt_algorithm: str = "RS256"
    sso_signing_key_pem: str = ""
    sso_signing_kid: str = "sso-1"
    sso_clients: Tuple[SsoClientConfig, ...] = ()
    sso_code_ttl_seconds: int = 60
    sso_id_token_ttl_seconds: int = 300
    sso_require_pkce: bool = True
    sso_mount_well_known_root: bool = True
    sso_token_rate_limit_ip: int = 30
    sso_token_rate_limit_client: int = 30
    # Tests / local HTTP. Production issuer must be https.
    sso_allow_http_issuer: bool = False

    def challenge_ttl(self) -> int:
        return max(30, int(self.two_factor_challenge_ttl_seconds or 300))

    def challenge_max_attempts(self) -> int:
        return max(1, int(self.two_factor_max_attempts or 5))

    def use_db_state(self) -> bool:
        return (self.state_backend or "db").lower() != "memory"

    def code_secret(self) -> str:
        return self.secret_key or self.jwt_secret

    def encryption_material(self) -> str:
        return self.file_encryption_key or self.secret_key or self.jwt_secret

    def effective_admin_password_min_length(self) -> int:
        if self.admin_password_min_length is None:
            return int(self.password_min_length)
        return int(self.admin_password_min_length)

    def effective_admin_access_token_expire_minutes(self) -> int:
        if self.admin_access_token_expire_minutes is None:
            return int(self.access_token_expire_minutes)
        return int(self.admin_access_token_expire_minutes)

    def sso_issuer_value(self) -> str:
        return (self.sso_issuer or "").strip().rstrip("/")

    def sso_alg(self) -> str:
        return (self.sso_jwt_algorithm or "RS256").strip().upper() or "RS256"

    def sso_configured(self) -> bool:
        if not self.sso_issuer_value() or not self.sso_clients:
            return False
        alg = self.sso_alg()
        if alg == "RS256":
            return bool((self.sso_signing_key_pem or "").strip())
        if alg == "HS256":
            return any(bool((c.client_secret or "").strip()) for c in self.sso_clients)
        return False

    def sso_client(self, client_id: Optional[str]) -> Optional[SsoClientConfig]:
        wanted = (client_id or "").strip()
        if not wanted:
            return None
        for client in self.sso_clients:
            if client.client_id == wanted:
                return client
        return None


_config: Optional[AccountKitConfig] = None


def set_config(config: AccountKitConfig) -> None:
    global _config
    _config = config


def get_config() -> AccountKitConfig:
    if _config is None:
        raise RuntimeError("account-kit is not configured")
    return _config
