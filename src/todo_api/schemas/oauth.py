from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OAuthBaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OAuthRedirectUriSchema(OAuthBaseSchema):
    redirect_uri: str = Field(min_length=1, max_length=2048)

    @field_validator("redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, value: str) -> str:
        parsed = urlsplit(value)

        if not parsed.scheme:
            raise ValueError("redirect_uri must be an absolute URI")

        if "#" in value:
            raise ValueError("redirect_uri must not contain a fragment")

        return value


class OAuthAuthorizationRequestSchema(OAuthRedirectUriSchema):
    response_type: Literal["code"]
    client_id: str = Field(min_length=1, max_length=128)
    state: str | None = Field(default=None, min_length=1, max_length=512)
    code_challenge: str = Field(
        min_length=43,
        max_length=43,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    code_challenge_method: Literal["S256"]
    scope: str = Field(default="", max_length=2048)


class OAuthTokenRequestSchema(OAuthRedirectUriSchema):
    grant_type: Literal["authorization_code"]
    client_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=512)
    code_verifier: str = Field(
        min_length=43,
        max_length=128,
        pattern=r"^[A-Za-z0-9\-._~]+$",
    )
