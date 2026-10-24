"""WeChat Mini Program QR login. Off unless ``AccountKitConfig.wechat_enabled``."""

from account_kit.wechat.service import delete_user_identities, invalidate_user_tickets

__all__ = ["delete_user_identities", "invalidate_user_tickets"]
