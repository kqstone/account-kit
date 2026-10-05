from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field

from account_kit.schemas import ApprovalStatus


class RoleBody(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    sort_order: int = 0
    description: Optional[str] = None
    is_default: bool = False
    allow_register: bool = False


class RolePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort_order: Optional[int] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    allow_register: Optional[bool] = None


class TierBody(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=50)
    sort_order: int = 0
    badge_color: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False


class TierPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort_order: Optional[int] = None
    badge_color: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


class AdminUserPatch(BaseModel):
    role: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    approval_status: Optional[ApprovalStatus] = None
    tier_code: Optional[str] = None


class RoleChangeCreate(BaseModel):
    requested_role: str = Field(min_length=1, max_length=50)


class RoleChangeReview(BaseModel):
    status: ApprovalStatus
