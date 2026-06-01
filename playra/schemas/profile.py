from datetime import datetime
from typing import Literal

from pydantic import BaseModel, HttpUrl, field_validator


class ProfileResponse(BaseModel):
    id: str
    role: Literal["suspended", "pending", "active", "admin"]
    username: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    created_at: datetime


class ProfileRequest(BaseModel):
    username: str | None = None
    avatar_url: HttpUrl | None = None

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError("username cannot be empty")
        return v


class RoleUpdateRequest(BaseModel):
    role: Literal["suspended", "pending", "active", "admin"]
