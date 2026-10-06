"""Shared account kit: one async user model for every app."""

from account_kit.router import mount_account
from account_kit.schema_setup import ensure_schema, ensure_schema_sync, init_db
from account_kit.seed import seed_defaults

__version__ = "0.2.2"

__all__ = ["ensure_schema", "ensure_schema_sync", "init_db", "mount_account", "seed_defaults", "__version__"]
