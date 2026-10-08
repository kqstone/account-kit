"""Optional avatar storage. Hosts supply save/delete/open callbacks; kit does not ship Pillow."""

from __future__ import annotations

import os
from typing import Any, Optional
from uuid import UUID

from fastapi.responses import FileResponse, Response, StreamingResponse

from account_kit.config import AccountKitConfig
from account_kit.i18n import account_error

AVATAR_MAX_BYTES = 2 * 1024 * 1024


def require_avatar(config: AccountKitConfig) -> None:
    if not config.avatar_enabled:
        raise account_error(501, "AVATAR_DISABLED")


def as_response(source: Any, media_type: str):
    media = media_type or "application/octet-stream"
    if isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        if not os.path.isfile(path):
            raise account_error(404, "AVATAR_NOT_FOUND")
        return FileResponse(path, media_type=media)
    if isinstance(source, (bytes, bytearray, memoryview)):
        return Response(content=bytes(source), media_type=media)
    return StreamingResponse(source, media_type=media)


async def save_avatar(
    config: AccountKitConfig,
    user_id: UUID,
    content: bytes,
    content_type: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    require_avatar(config)
    if config.avatar_save is None:
        raise account_error(501, "AVATAR_STORAGE_UNCONFIGURED")
    if not content:
        raise account_error(400, "AVATAR_EMPTY")
    if len(content) > AVATAR_MAX_BYTES:
        raise account_error(400, "AVATAR_TOO_LARGE")
    return await config.avatar_save(user_id, content, content_type, filename)


async def delete_avatar(config: AccountKitConfig, avatar_path: Optional[str]) -> None:
    require_avatar(config)
    if config.avatar_delete is None or not avatar_path:
        return
    try:
        await config.avatar_delete(avatar_path)
    except OSError:
        pass


async def serve_avatar(config: AccountKitConfig, avatar_path: Optional[str]):
    require_avatar(config)
    if not avatar_path:
        raise account_error(404, "AVATAR_NOT_FOUND")
    if config.avatar_open is not None:
        try:
            source, media_type = await config.avatar_open(avatar_path)
        except FileNotFoundError as exc:
            raise account_error(404, "AVATAR_NOT_FOUND") from exc
        return as_response(source, media_type)
    if os.path.isfile(avatar_path):
        return FileResponse(avatar_path, media_type="image/jpeg")
    raise account_error(404, "AVATAR_NOT_FOUND")
