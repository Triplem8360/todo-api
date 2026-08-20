from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from todo_api.utils.email import normalize_email


def _normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.strip()) or None


class UserCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255, examples=["user@example.com"])
    full_name: str | None = Field(default=None, max_length=150, examples=["Ali Panahi"])
    password: SecretStr = Field(min_length=8, max_length=128, examples=["strong-password-123"])

    @field_validator("email")
    @classmethod
    def normalize_email_field(cls, value: EmailStr) -> str:
        return normalize_email(str(value))

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        return _normalize_name(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if any(char.isspace() for char in password):
            raise ValueError("Password must not contain whitespace.")
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValueError("Password must contain at least one letter and one number.")
        return value


class UserProfileUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(max_length=150, examples=["Ali Panahi"])

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        return _normalize_name(value)


class UserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime


class RegistrationResponseSchema(UserResponseSchema):
    verification_email_queued: bool
    verification_email_sent: bool = Field(
        deprecated=True,
        description=(
            "Deprecated compatibility alias for verification_email_queued; background delivery "
            "may still fail after the task is accepted."
        ),
    )


class EmailVerificationResendRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255, examples=["user@example.com"])

    @field_validator("email")
    @classmethod
    def normalize_email_field(cls, value: EmailStr) -> str:
        return normalize_email(str(value))


class EmailVerificationAcceptedSchema(BaseModel):
    detail: Literal["If an unverified account exists, a verification email will be sent."] = (
        "If an unverified account exists, a verification email will be sent."
    )


class EmailVerificationResponseSchema(BaseModel):
    email_verified: Literal[True] = True
    detail: Literal["Email verified successfully."] = "Email verified successfully."
