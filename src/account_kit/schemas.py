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
    language: str = "zh"


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
    # Host-only. account-kit does not store consent; dedd reads it in on_registered.
    doctor_consent_version: Optional[str] = None

    @field_validator("birth_year_month", mode="before")
    @classmethod
    def _birth(cls, value):
        return _birth(value)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str


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

    @field_serializer("birth_year_month")
    def _serialize_birth(self, value):
        return format_birth_year_month(value) if value is not None and not isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileResponse(BaseModel):
    user: UserResponse
    access_token: Optional[str] = None
    token_type: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    detail: str
