from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailTestRequestSchema(BaseModel):
    subject: str = Field(default="Todo API SMTP test", min_length=1, max_length=200)
    body: str = Field(
        default="If you can read this in smtp4dev, email delivery is configured correctly.",
        min_length=1,
        max_length=20_000,
    )
    subtype: Literal["plain", "html"] = "plain"

    @field_validator("subject")
    @classmethod
    def strip_subject(cls, value: str) -> str:
        subject = value.strip()
        if not subject:
            raise ValueError("Email subject must not be blank.")
        return subject


class EmailDeliveryResponseSchema(BaseModel):
    status: Literal["sent", "suppressed"]
    recipient: EmailStr


class SMTPConnectionResponseSchema(BaseModel):
    status: Literal["ok", "suppressed"]
    server: str
    port: int
    starttls: bool
    ssl_tls: bool
    use_credentials: bool
    validate_certs: bool
