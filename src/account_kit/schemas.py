from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

from account_kit.profile import format_birth_year_month, parse_birth_year_month

UserGender = Literal["male", "female"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


def _birth(value):
    if value is None or value == "":
        return None
    return format_birth_year_month(parse_birth_year_month(value))


class SendCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "reset_password", "change_password"]
    language: Optional[str] = None


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "reset_password", "change_password"]
    code: str = Field(min_length=6, max_length=6)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str
    code: str = Field(min_length=6, max_length=6)
    full_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("full_name", "real_name"))
    institution: Optional[str] = None
    gender: Optional[UserGender] = None
    birth_year_month: Optional[str] = None
    role: Optional[str] = None
    # Host-only. account-kit does not store consent; the host app reads it in on_registered.
    doctor_consent_version: Optional[str] = None

    @field_validator("birth_year_month", mode="before")
    @classmethod
    def _birth(cls, value):
        return _birth(value)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    code: Optional[str] = None


class UserProfileUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    institution: Optional[str] = None
    gender: Optional[UserGender] = None
    birth_year_month: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    code: Optional[str] = None
    # Code sent to the new address by POST /me/email/send-code (0.2.2).
    email_code: Optional[str] = None

    @field_validator("birth_year_month", mode="before")
    @classmethod
    def _birth(cls, value):
        return _birth(value)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    institution: Optional[str] = None
    gender: Optional[UserGender] = None
    birth_year_month: Optional[str] = None
    role: str
    is_admin: bool
    is_active: bool
    approval_status: str
    has_custom_avatar: bool = False
    pending_role: Optional[str] = None
    tier: Optional[str] = None
    tier_name: Optional[str] = None
    tier_badge_color: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("birth_year_month", mode="before")
    @classmethod
    def _birth(cls, value):
        # SQLAlchemy stores Date; model_validate(user) needs str before type check.
        return _birth(value)

    @field_serializer("birth_year_month")
    def _serialize_birth(self, value):
        return format_birth_year_month(value) if value is not None and not isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Only present with ``refresh_token_enabled`` (routes exclude None fields).
    refresh_token: Optional[str] = None
    refresh_expires_in: Optional[int] = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(default=None, max_length=512)
    all_devices: bool = False


class ChangeEmailCodeRequest(BaseModel):
    new_email: EmailStr
    password: Optional[str] = None
    language: Optional[str] = None


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    code: str = Field(min_length=1, max_length=16)
    password: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    password: str
    code: Optional[str] = ""
    recovery_code: Optional[str] = ""
    email_code: Optional[str] = ""


class LanguageRequest(BaseModel):
    language: Optional[str] = None


class ProfileResponse(BaseModel):
    user: UserResponse
    access_token: Optional[str] = None
    token_type: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    detail: str
