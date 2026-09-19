"""Authentication and user account schemas."""

import datetime
from typing import Annotated
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

PasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class UserRegister(BaseModel):
    """Payload schema for user account registration."""

    email: EmailStr = Field(
        ...,
        description="Valid and unique user email address",
        examples=["teacher@example.com"],
    )
    password: PasswordStr = Field(
        ...,
        description="Plaintext password (minimum 8 characters)",
        examples=["StrongPassword123!"],
    )


class UserLogin(BaseModel):
    """Payload schema for user authentication."""

    email: EmailStr = Field(
        ...,
        description="User email address",
        examples=["teacher@example.com"],
    )
    password: str = Field(
        ...,
        description="Plaintext password",
        examples=["StrongPassword123!"],
    )


class UserResponse(BaseModel):
    """Public user account details schema (excludes password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime.datetime


class TokenResponse(BaseModel):
    """JWT bearer access token response schema."""

    access_token: str
    token_type: str = "bearer"
