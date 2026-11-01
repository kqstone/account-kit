"""Optional OIDC Identity Provider. Off unless ``AccountKitConfig.sso_idp_enabled``."""

from account_kit.config import SsoClientConfig
from account_kit.sso.rp import (
    MemoryDiscoveryCache,
    discover,
    exchange_authorization_code,
    fetch_userinfo,
    verify_id_token,
)
from account_kit.sso.service import invalidate_user_codes

__all__ = [
    "MemoryDiscoveryCache",
    "SsoClientConfig",
    "discover",
    "exchange_authorization_code",
    "fetch_userinfo",
    "invalidate_user_codes",
    "verify_id_token",
]
