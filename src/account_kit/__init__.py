"""Shared account kit: one async user model for every app."""

from account_kit.admin_setup import AdminSetupError, ensure_admin
from account_kit.approval import assert_login_allowed, count_pending, provision_user, set_user_approval
from account_kit.bind_target import lookup_bind_user, verify_bind_target
from account_kit.bind_ticket import (
    BIND_TICKET_TTL_SECONDS,
    attach_mfa_challenge,
    consume_bind_ticket,
    issue_bind_ticket,
    load_bind_ticket,
)
from account_kit.i18n import AccountError
from account_kit.router import mount_account
from account_kit.schema_setup import ensure_schema, ensure_schema_sync, init_db
from account_kit.seed import seed_defaults
from account_kit.service import create_user

__version__ = "0.6.0"

__all__ = [
    "AccountError",
    "AdminSetupError",
    "BIND_TICKET_TTL_SECONDS",
    "assert_login_allowed",
    "attach_mfa_challenge",
    "consume_bind_ticket",
    "count_pending",
    "create_user",
    "ensure_admin",
    "ensure_schema",
    "ensure_schema_sync",
    "init_db",
    "issue_bind_ticket",
    "load_bind_ticket",
    "lookup_bind_user",
    "mount_account",
    "provision_user",
    "seed_defaults",
    "set_user_approval",
    "verify_bind_target",
    "__version__",
]
