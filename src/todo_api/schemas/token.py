from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BaseTokenPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    sub: str = Field(min_length=1)
    exp: datetime
    iat: datetime
    jti: str = Field(min_length=32)
    iss: str = Field(min_length=1)
    aud: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_expiration(self) -> BaseTokenPayload:
        if self.exp <= self.iat:
            raise ValueError("exp must be later than iat")

        return self


class AccessTokenPayload(BaseTokenPayload):
    token_type: Literal["access"] = Field(alias="type")


class RefreshTokenPayload(BaseTokenPayload):
    session_id: str = Field(alias="sid", min_length=32)
    token_type: Literal["refresh"] = Field(alias="type")


class TokenResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(
        gt=0,
        description="Access-token lifetime in seconds.",
    )


class BrowserSessionResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: Literal[True] = True
    expires_in: int = Field(
        gt=0,
        description="Access-cookie lifetime in seconds.",
    )


class RefreshTokenRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    refresh_token: str = Field(min_length=1)
