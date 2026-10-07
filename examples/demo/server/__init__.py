"""Shared demo FastAPI host for account-kit (no Docker)."""

from .app import create_app

__all__ = ["create_app"]
