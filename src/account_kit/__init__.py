"""Shared account kit: one async user model for every app."""

from account_kit.router import mount_account
from account_kit.schema_setup import init_db
from account_kit.seed import seed_defaults

__version__ = "0.2.0"

__all__ = ["init_db", "mount_account", "seed_defaults", "__version__"]
