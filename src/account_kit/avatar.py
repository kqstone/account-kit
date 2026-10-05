"""Optional avatar storage. Hosts supply save/delete/open callbacks; kit does not ship Pillow."""

from __future__ import annotations

import os
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from account_kit.config import AccountKitConfig

AVATAR_MAX_BYTES = 2 * 1024 * 1024


def require_avatar(config: AccountKitConfig) -> None:
    if not config.avatar_enabled:
        raise HTTPException(status_code=501, detail="头像功能未启用")


def as_response(source: Any, media_type: str):
    media = media_type or "application/octet-stream"
    if isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Avatar not found")
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
        raise HTTPException(status_code=501, detail="头像存储未配置")
    if not content:
        raise HTTPException(status_code=400, detail="请选择头像图片")
    if len(content) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="头像不能超过 2MB")
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
        raise HTTPException(status_code=404, detail="Avatar not found")
    if config.avatar_open is not None:
        try:
            source, media_type = await config.avatar_open(avatar_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Avatar not found") from exc
        return as_response(source, media_type)
    if os.path.isfile(avatar_path):
        return FileResponse(avatar_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Avatar not found")
