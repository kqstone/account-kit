"""Shared account kit: one async user model for every app."""

from account_kit.admin_setup import AdminSetupError, ensure_admin
from account_kit.i18n import AccountError
from account_kit.router import mount_account
from account_kit.schema_setup import ensure_schema, ensure_schema_sync, init_db
from account_kit.seed import seed_defaults

__version__ = "0.3.0"

__all__ = [
    "AccountError",
    "AdminSetupError",
    "ensure_admin",
    "ensure_schema",
    "ensure_schema_sync",
    "init_db",
    "mount_account",
    "seed_defaults",
    "__version__",
]
