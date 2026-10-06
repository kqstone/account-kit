"""Account tables. All live in schema ``auth``. No quota or product columns."""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from account_kit.db import Base

AUTH = {"schema": "auth"}


class Role(Base):
    """Custom role catalog. ``admin`` is not a role."""

    __tablename__ = "roles"
    __table_args__ = AUTH

    code = Column(String(50), primary_key=True)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    allow_register = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserTier(Base):
    """Tier catalog only: which plans exist, not what they limit."""

    __tablename__ = "user_tiers"
    __table_args__ = AUTH

    code = Column(String(20), primary_key=True)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    badge_color = Column(String(20), nullable=True)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = AUTH

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String(100), nullable=True)
    institution = Column(String(200), nullable=True)
    gender = Column(String(10), nullable=True)
    birth_year_month = Column(Date, nullable=True)
    avatar_path = Column(String, nullable=True)
    role = Column(String(50), ForeignKey("auth.roles.code"), nullable=False)
    # Backend access. Orthogonal to ``role``.
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    # pending | approved | rejected
    approval_status = Column(String(20), nullable=False, default="approved", server_default="approved")
    approved_at = Column(DateTime(timezone=True), nullable=True)
    current_session_id = Column(String(64), nullable=True)
    session_last_seen_at = Column(DateTime(timezone=True), nullable=True)
    session_device_name = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def has_custom_avatar(self) -> bool:
        return bool(self.avatar_path)


class UserTierAssignment(Base):
    __tablename__ = "user_tier_assignments"
    __table_args__ = AUTH

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier_code = Column(String(20), ForeignKey("auth.user_tiers.code", onupdate="CASCADE"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    __table_args__ = AUTH

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(100), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    purpose = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False, server_default="false")


class RoleChangeRequest(Base):
    __tablename__ = "role_change_requests"
    __table_args__ = AUTH

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    from_role = Column(String(50), nullable=False)
    to_role = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=True)


class UserTwoFactor(Base):
    __tablename__ = "user_two_factor"
    __table_args__ = AUTH

    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    secret = Column(String(512), nullable=True)
    pending_secret = Column(String(512), nullable=True)
    pending_created_at = Column(DateTime(timezone=True), nullable=True)
    last_step = Column(BigInteger, nullable=True)
    enabled_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TwoFactorRecoveryCode(Base):
    __tablename__ = "two_factor_recovery_codes"
    __table_args__ = AUTH

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        AUTH,
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False)
    device_name = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"
    __table_args__ = AUTH

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    event = Column(String(64), nullable=False, index=True)
    ip = Column(String(64), nullable=True)
    device_name = Column(String(128), nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# --- 0.2.2: new tables only (no column changes), so ``create_all`` / ``init_db``
# adds them to an existing database. Hand-written SQL: docs/migrations/0.2.2.sql.


class RateLimitCounter(Base):
    """Fixed-window counters: send/login rate limits, wrong-code attempts, login
    failures for the captcha gate. One row per key, updated with an atomic upsert."""

    __tablename__ = "rate_limit_counters"
    __table_args__ = AUTH

    key = Column(String(255), primary_key=True)
    count = Column(Integer, nullable=False, default=0, server_default="0")
    window_start = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class TwoFactorChallenge(Base):
    """Pending second login step (password already verified)."""

    __tablename__ = "two_factor_challenges"
    __table_args__ = AUTH

    token_hash = Column(String(64), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    pw_fp = Column(String(64), nullable=False)
    device_name = Column(String(128), nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    passed = Column(Boolean, nullable=False, default=False, server_default="false")
    method = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class RefreshToken(Base):
    """Opaque refresh tokens, stored as SHA-256. Rotation keeps ``family_id``; a
    rotated token presented again revokes the whole family (reuse detection)."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        AUTH,
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=True)
    device_name = Column(String(128), nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    # rotated | logout | password_changed | two_factor_disabled | reuse_detected |
    # session_replaced | admin | deleted | expired
    revoked_reason = Column(String(32), nullable=True)
    replaced_by = Column(UUID(as_uuid=True), nullable=True)


class CaptchaChallenge(Base):
    """Built-in image captcha answers (hashed), single use."""

    __tablename__ = "captcha_challenges"
    __table_args__ = AUTH

    id = Column(String(64), primary_key=True)
    answer_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
