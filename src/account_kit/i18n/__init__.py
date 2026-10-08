"""Per-request locale, message lookup, and AccountError."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Dict, Mapping, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from account_kit.i18n.messages import DEFAULT_LOCALE, MESSAGES, SESSION_REPLACED, SUPPORTED_LOCALES

__all__ = [
    "DEFAULT_LOCALE",
    "MESSAGES",
    "SESSION_REPLACED",
    "SUPPORTED_LOCALES",
    "AccountError",
    "LocaleMiddleware",
    "account_error",
    "account_error_handler",
    "attach_locale_dependency",
    "canonicalize_locale",
    "email_lang_suffix",
    "error_code_of",
    "get_locale",
    "normalize_locale",
    "parse_accept_language",
    "resolve_email_language",
    "resolve_request_locale",
    "t",
    "validation_error_handler",
]

_locale_var: ContextVar[str] = ContextVar("account_kit_locale", default=DEFAULT_LOCALE)


def normalize_locale(raw: Optional[str]) -> str:
    """Map aliases onto ``zh-CN`` / ``en``. Unknown tags are returned unchanged (stripped)."""
    text = (raw or "").strip().replace("_", "-")
    if not text:
        return ""
    low = text.lower()
    if low == "zh" or low.startswith("zh-"):
        return "zh-CN"
    if low == "en" or low.startswith("en-"):
        return "en"
    return text


def canonicalize_locale(raw: Optional[str], supported: Optional[Tuple[str, ...]] = None, default: Optional[str] = None) -> str:
    allowed = supported or SUPPORTED_LOCALES
    fallback = normalize_locale(default) or DEFAULT_LOCALE
    if fallback not in allowed:
        fallback = DEFAULT_LOCALE if DEFAULT_LOCALE in allowed else (allowed[0] if allowed else DEFAULT_LOCALE)
    norm = normalize_locale(raw)
    if norm in allowed:
        return norm
    return fallback


def get_locale() -> str:
    return _locale_var.get()


def bind_locale(locale: str) -> Token:
    return _locale_var.set(locale or DEFAULT_LOCALE)


def reset_locale(token: Token) -> None:
    _locale_var.reset(token)


def email_lang_suffix(locale: Optional[str] = None) -> str:
    """``zh`` / ``en`` for templates and the host ``mailer`` callback."""
    loc = canonicalize_locale(locale or get_locale())
    return "en" if loc == "en" else "zh"


def resolve_email_language(body_language: Optional[str]) -> str:
    """Explicit valid body ``language`` wins; otherwise the request locale. Returns ``zh``/``en``."""
    if body_language and str(body_language).strip():
        norm = normalize_locale(body_language)
        if norm in ("zh-CN", "en"):
            return "en" if norm == "en" else "zh"
    return email_lang_suffix()


def _override_table(locale: str) -> Mapping[str, str]:
    try:
        from account_kit.config import get_config

        cfg = get_config()
    except Exception:
        return {}
    raw = getattr(cfg, "messages_override", None) or {}
    if not isinstance(raw, dict):
        return {}
    table = raw.get(locale) or raw.get(normalize_locale(locale)) or {}
    return table if isinstance(table, dict) else {}


def t(code: str, params: Optional[Mapping[str, Any]] = None, *, locale: Optional[str] = None) -> str:
    loc = canonicalize_locale(locale or get_locale())
    template = (
        _override_table(loc).get(code)
        or MESSAGES.get(loc, {}).get(code)
        or MESSAGES.get(DEFAULT_LOCALE, {}).get(code)
        or code
    )
    if params:
        try:
            return str(template).format(**params)
        except (KeyError, IndexError, ValueError):
            return str(template)
    return str(template)


def parse_accept_language(header: str) -> Tuple[str, ...]:
    items = []
    for part in (header or "").split(","):
        token = part.strip()
        if not token:
            continue
        tag, _, rest = token.partition(";")
        q = 1.0
        if rest.strip().lower().startswith("q="):
            try:
                q = float(rest.strip()[2:])
            except ValueError:
                q = 0.0
        items.append((tag.strip(), q))
    items.sort(key=lambda item: -item[1])
    return tuple(tag for tag, _q in items if tag)


def resolve_request_locale(request: Request) -> str:
    from account_kit.config import get_config

    try:
        config = get_config()
    except Exception:
        return DEFAULT_LOCALE
    supported = tuple(config.supported_locales or SUPPORTED_LOCALES)
    default = config.default_locale or DEFAULT_LOCALE

    if config.locale_resolver is not None:
        try:
            got = config.locale_resolver(request)
        except Exception:
            got = None
        if got:
            return canonicalize_locale(str(got), supported, default)

    header_name = config.locale_header or "X-Locale"
    raw_header = request.headers.get(header_name) or request.headers.get(header_name.lower())
    if raw_header:
        return canonicalize_locale(raw_header, supported, default)

    query_name = config.locale_query or "locale"
    raw_query = request.query_params.get(query_name)
    if raw_query:
        return canonicalize_locale(raw_query, supported, default)

    if config.negotiate_accept_language:
        accept = request.headers.get("accept-language") or ""
        for tag in parse_accept_language(accept):
            norm = normalize_locale(tag)
            if norm in supported:
                return norm

    return canonicalize_locale(default, supported, default)


def error_code_of(exc: BaseException) -> Optional[str]:
    code = getattr(exc, "kit_code", None)
    return str(code) if code else None


class AccountError(HTTPException):
    """Kit HTTP error. ``detail`` keeps the historical string-or-dict shape; handler adds top-level ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        as_dict: bool = False,
        message_key: Optional[str] = None,
    ) -> None:
        self.kit_code = code
        self.kit_params: Dict[str, Any] = dict(params or {})
        self.kit_extra: Dict[str, Any] = dict(extra or {})
        self.message_key = message_key or code
        if code == "SESSION_REPLACED":
            message = SESSION_REPLACED
            detail: Any = SESSION_REPLACED
        else:
            message = t(self.message_key, self.kit_params or None)
            if as_dict or extra is not None:
                detail = {"code": code, "message": message, **self.kit_extra}
            else:
                detail = message
        super().__init__(status_code=status_code, detail=detail, headers=headers)


def account_error(
    status_code: int,
    code: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    as_dict: bool = False,
    message_key: Optional[str] = None,
) -> AccountError:
    return AccountError(
        status_code,
        code,
        params=params,
        extra=extra,
        headers=headers,
        as_dict=as_dict,
        message_key=message_key,
    )


async def account_error_handler(_request: Request, exc: AccountError) -> JSONResponse:
    body: Dict[str, Any] = {"detail": exc.detail, "code": exc.kit_code}
    if exc.kit_params:
        body["params"] = exc.kit_params
    return JSONResponse(status_code=exc.status_code, content=body, headers=dict(exc.headers) if exc.headers else None)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "code": "VALIDATION_ERROR"})


async def set_request_locale(request: Request):
    token = bind_locale(resolve_request_locale(request))
    try:
        yield
    finally:
        reset_locale(token)


class LocaleMiddleware:
    """Pure ASGI middleware: bind the request locale for the duration of the call."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        token = bind_locale(resolve_request_locale(request))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_locale(token)


def attach_locale_dependency(router) -> None:
    from fastapi import Depends

    for dep in router.dependencies:
        if getattr(dep, "dependency", None) is set_request_locale:
            return
    router.dependencies.append(Depends(set_request_locale))
