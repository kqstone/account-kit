"""Shared account kit: one async user model for every app."""

from account_kit.admin_setup import AdminSetupError, ensure_admin
from account_kit.approval import (
    assert_login_allowed,
    count_pending,
    notify_admins_pending,
    notify_user_approval_decision,
    provision_user,
    set_user_approval,
)
from account_kit.bind_target import lookup_bind_user, verify_bind_target
from account_kit.bind_ticket import (
    BIND_TICKET_TTL_SECONDS,
    attach_mfa_challenge,
    consume_bind_ticket,
    discard_bind_mfa_challenge,
    find_bind_ticket_by_mfa,
    issue_bind_ticket,
    load_bind_ticket,
)
from account_kit.i18n import AccountError
from account_kit.router import mount_account
from account_kit.schema_setup import ensure_schema, ensure_schema_sync, init_db
from account_kit.seed import seed_defaults
from account_kit.service import create_user
from account_kit.two_factor.challenges import discard_challenge

__version__ = "0.7.1"

__all__ = [
    "AccountError",
    "AdminSetupError",
    "BIND_TICKET_TTL_SECONDS",
    "assert_login_allowed",
    "attach_mfa_challenge",
    "consume_bind_ticket",
    "count_pending",
    "create_user",
    "discard_bind_mfa_challenge",
    "discard_challenge",
    "ensure_admin",
    "ensure_schema",
    "ensure_schema_sync",
    "find_bind_ticket_by_mfa",
    "init_db",
    "issue_bind_ticket",
    "load_bind_ticket",
    "lookup_bind_user",
    "mount_account",
    "notify_admins_pending",
    "notify_user_approval_decision",
    "provision_user",
    "seed_defaults",
    "set_user_approval",
    "verify_bind_target",
    "__version__",
]
