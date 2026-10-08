"""Minimal FastAPI host: setup wizard, then account-kit on a sub-app."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.types import ASGIApp, Receive, Scope, Send

from account_kit import ensure_admin, init_db, mount_account, seed_defaults
from account_kit.admin_setup import AdminSetupError
from account_kit.config import AccountKitConfig, SmtpConfig
from account_kit.i18n import canonicalize_locale, normalize_locale, parse_accept_language

from .mailer import Outbox, make_mailer

DEMO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / ".demo-config.json"
BRAND = "Account Kit Demo"

DEMO_MESSAGES: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "NOT_INITIALIZED": "请先完成初始化",
        "ALREADY_INITIALIZED": "已经初始化，setup 写接口已锁死",
        "DB_UNREACHABLE": "无法连接数据库: {exc}",
        "INIT_FAILED": "初始化失败: {exc}",
        "MAIL_MODE_INVALID": "mail_mode 必须是 console 或 smtp",
        "SMTP_HOST_REQUIRED": "smtp 模式需要 smtp.host",
        "SPA_NOT_FOUND": "资源不存在",
    },
    "en": {
        "NOT_INITIALIZED": "Please complete setup first",
        "ALREADY_INITIALIZED": "Already initialized; setup write APIs are locked",
        "DB_UNREACHABLE": "Cannot reach the database: {exc}",
        "INIT_FAILED": "Setup failed: {exc}",
        "MAIL_MODE_INVALID": "mail_mode must be console or smtp",
        "SMTP_HOST_REQUIRED": "smtp mode requires smtp.host",
        "SPA_NOT_FOUND": "Not found",
    },
}


def demo_locale(request: Optional[Request] = None) -> str:
    if request is None:
        return "zh-CN"
    header = request.headers.get("X-Locale") or request.headers.get("x-locale")
    if header:
        return canonicalize_locale(header)
    query = request.query_params.get("locale")
    if query:
        return canonicalize_locale(query)
    accept = request.headers.get("accept-language") or ""
    for tag in parse_accept_language(accept):
        norm = normalize_locale(tag)
        if norm in ("zh-CN", "en"):
            return norm
    return "zh-CN"


def demo_text(code: str, request: Optional[Request] = None, **params: Any) -> str:
    loc = demo_locale(request)
    template = DEMO_MESSAGES.get(loc, DEMO_MESSAGES["zh-CN"]).get(code) or DEMO_MESSAGES["zh-CN"][code]
    try:
        return template.format(**params) if params else template
    except (KeyError, IndexError, ValueError):
        return template


FEATURE_DEFAULTS: Dict[str, Any] = {
    "refresh": True,
    "captcha": True,
    "self_delete": True,
    "two_factor_email": True,
    "require_approval": False,
    "two_factor": True,
    "logout": True,
    "audit_log": True,
    "role_change": True,
    "session_mode": "stateless",
    "captcha_fail_threshold": 3,
}


def demo_root() -> Path:
    return DEMO_ROOT


def config_path() -> Path:
    raw = os.environ.get("DEMO_CONFIG_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_CONFIG_PATH


def web_choice() -> str:
    value = (os.environ.get("DEMO_WEB") or "vue").strip().lower()
    return value if value in ("vue", "react") else "vue"


def database_url(db: Dict[str, Any]) -> str:
    user = quote_plus(str(db["user"]))
    password = quote_plus(str(db.get("password") or ""))
    host = str(db["host"]).strip()
    port = int(db.get("port") or 5432)
    name = str(db["database"]).strip()
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def load_config(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class DbBody(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = ""
    database: str = Field(min_length=1)


class AdminBody(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6)


class SmtpBody(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""
    tls: bool = True


class InitBody(BaseModel):
    db: DbBody
    admin: AdminBody
    features: Dict[str, Any] = Field(default_factory=dict)
    mail_mode: str = "console"
    smtp: Optional[SmtpBody] = None


class Runtime:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.data: Optional[Dict[str, Any]] = None
        self.engine = None
        self.sessions = None
        self.kit_app: Optional[FastAPI] = None
        self.outbox = Outbox()
        self.error: Optional[str] = None
        self.mailer = make_mailer(
            self.outbox,
            smtp_provider=lambda: (self.data or {}).get("smtp") if (self.data or {}).get("mail_mode") == "smtp" else None,
            brand_provider=lambda: BRAND,
        )

    @property
    def ready(self) -> bool:
        return self.kit_app is not None


class KitDispatch:
    """Send /api/auth and /api/admin to the kit sub-app once it exists.

    The sub-app is built with ``mount_account`` in one shot (never mutated
    after serving starts), so FastAPI routing/OpenAPI stay consistent.
    """

    def __init__(self, app: ASGIApp, runtime: Runtime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path") or ""
            if path.startswith("/api/auth") or path.startswith("/api/admin"):
                kit = self.runtime.kit_app
                if kit is None:
                    request = Request(scope)
                    response = JSONResponse(
                        {
                            "detail": {
                                "code": "NOT_INITIALIZED",
                                "message": demo_text("NOT_INITIALIZED", request),
                            }
                        },
                        status_code=503,
                    )
                    await response(scope, receive, send)
                    return
                await kit(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def test_postgres(db: DbBody, request: Optional[Request] = None) -> None:
    try:
        conn = await asyncpg.connect(
            host=db.host,
            port=db.port,
            user=db.user,
            password=db.password,
            database=db.database,
            timeout=5,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "DB_UNREACHABLE", "message": demo_text("DB_UNREACHABLE", request, exc=exc)},
        ) from exc
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


def merge_features(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(FEATURE_DEFAULTS)
    if raw:
        out.update(raw)
    mode = str(out.get("session_mode") or "stateless")
    if mode not in ("stateless", "single_device"):
        mode = "stateless"
    out["session_mode"] = mode
    try:
        out["captcha_fail_threshold"] = max(1, int(out.get("captcha_fail_threshold") or 3))
    except (TypeError, ValueError):
        out["captcha_fail_threshold"] = 3
    for key in (
        "refresh",
        "captcha",
        "self_delete",
        "two_factor_email",
        "require_approval",
        "two_factor",
        "logout",
        "audit_log",
        "role_change",
    ):
        out[key] = bool(out.get(key))
    return out


def build_kit_config(runtime: Runtime) -> AccountKitConfig:
    data = runtime.data or {}
    features = merge_features(data.get("features"))
    smtp_raw = data.get("smtp") or {}
    return AccountKitConfig(
        jwt_secret=data["jwt_secret"],
        brand_name=BRAND,
        session_mode=features["session_mode"],
        require_approval=features["require_approval"],
        two_factor_enabled=features["two_factor"],
        two_factor_email_enabled=features["two_factor_email"],
        refresh_token_enabled=features["refresh"],
        captcha_builtin=features["captcha"],
        captcha_fail_threshold=features["captcha_fail_threshold"],
        self_delete_enabled=features["self_delete"],
        logout_enabled=features["logout"],
        logout_path="/logout",
        audit_log_enabled=features["audit_log"],
        role_change_enabled=features["role_change"],
        state_backend="db",
        profile_email_change="verify",
        change_email_require_password=True,
        change_password_require_email_code=False,
        mailer=runtime.mailer,
        admin_login_lockout_attempts=5,
        admin_login_lockout_seconds=900,
        negotiate_accept_language=True,
        smtp=SmtpConfig(
            host=smtp_raw.get("host") or "",
            port=int(smtp_raw.get("port") or 587),
            user=smtp_raw.get("user") or "",
            password=smtp_raw.get("password") or "",
            from_email=smtp_raw.get("from_email") or "",
            tls=bool(smtp_raw.get("tls", True)),
        ),
    )


async def activate(runtime: Runtime, admin: Optional[AdminBody] = None) -> None:
    if runtime.data is None:
        raise RuntimeError("missing demo config")
    kit_config = build_kit_config(runtime)
    engine = create_async_engine(database_url(runtime.data["db"]), pool_pre_ping=True)
    try:
        await init_db(engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            await seed_defaults(session)
            if admin is not None:
                try:
                    await ensure_admin(
                        session, admin.username, admin.email, admin.password, config=kit_config
                    )
                except AdminSetupError as exc:
                    raise exc.http() from exc

        async def get_db():
            async with sessions() as session:
                yield session

        kit = FastAPI(title="account-kit", docs_url=None, redoc_url=None, openapi_url=None)
        mount_account(kit, get_db, kit_config)
    except Exception:
        await engine.dispose()
        raise
    if runtime.engine is not None:
        await runtime.engine.dispose()
    runtime.engine = engine
    runtime.sessions = sessions
    runtime.kit_app = kit
    runtime.error = None


def public_status(runtime: Runtime) -> Dict[str, Any]:
    data = runtime.data or {}
    features = merge_features(data.get("features")) if data else None
    return {
        "initialized": runtime.ready,
        "features": features,
        "mail_mode": data.get("mail_mode") if data else None,
        "web": web_choice(),
        "error": runtime.error,
    }


def _raise_if_initialized(runtime: Runtime, request: Optional[Request] = None) -> None:
    if runtime.ready:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_INITIALIZED", "message": demo_text("ALREADY_INITIALIZED", request)},
        )


def create_app() -> FastAPI:
    runtime = Runtime()
    path = config_path()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if path.is_file():
            try:
                runtime.data = load_config(path)
                await activate(runtime)
            except Exception as exc:
                runtime.error = str(exc)
                runtime.kit_app = None
                print(f"[demo] startup failed: {exc}", flush=True)
        yield
        if runtime.engine is not None:
            await runtime.engine.dispose()
            runtime.engine = None
            runtime.kit_app = None

    app = FastAPI(title="account-kit demo", lifespan=lifespan)
    app.state.runtime = runtime

    @app.get("/api/setup/status")
    async def setup_status():
        return public_status(runtime)

    @app.post("/api/setup/test-db")
    async def setup_test_db(body: DbBody, request: Request):
        _raise_if_initialized(runtime, request)
        await test_postgres(body, request)
        return {"ok": True}

    @app.post("/api/setup/init")
    async def setup_init(body: InitBody, request: Request):
        async with runtime.lock:
            _raise_if_initialized(runtime, request)
            mail_mode = (body.mail_mode or "console").strip().lower()
            if mail_mode not in ("console", "smtp"):
                raise HTTPException(status_code=400, detail=demo_text("MAIL_MODE_INVALID", request))
            if mail_mode == "smtp" and not (body.smtp and body.smtp.host):
                raise HTTPException(status_code=400, detail=demo_text("SMTP_HOST_REQUIRED", request))
            await test_postgres(body.db, request)
            features = merge_features(body.features)
            stored = {
                "db": body.db.model_dump(),
                "admin": {"username": body.admin.username, "email": str(body.admin.email)},
                "features": features,
                "mail_mode": mail_mode,
                "smtp": body.smtp.model_dump() if body.smtp else None,
                "jwt_secret": secrets.token_urlsafe(48),
            }
            previous = runtime.data
            runtime.data = stored
            try:
                await activate(runtime, admin=body.admin)
            except HTTPException:
                runtime.data = previous
                runtime.kit_app = None
                raise
            except Exception as exc:
                runtime.data = previous
                runtime.kit_app = None
                runtime.error = str(exc)
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INIT_FAILED", "message": demo_text("INIT_FAILED", request, exc=exc)},
                ) from exc
            save_config(path, stored)
            return {
                "initialized": True,
                "admin": stored["admin"],
                "features": features,
                "mail_mode": mail_mode,
            }

    @app.get("/api/demo/outbox")
    async def demo_outbox(request: Request):
        email = request.query_params.get("email")
        purpose = request.query_params.get("purpose")
        items = runtime.outbox.list()
        if email:
            email_l = email.strip().lower()
            items = [item for item in items if item["to"].lower() == email_l]
        if purpose:
            items = [item for item in items if item["purpose"] == purpose]
        return {"items": items}

    dist = demo_root() / f"web-{web_choice()}" / "dist"
    if (dist / "index.html").is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        async def spa(full_path: str, request: Request):
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail=demo_text("SPA_NOT_FOUND", request))
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_relative_to(dist.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    app.add_middleware(KitDispatch, runtime=runtime)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
