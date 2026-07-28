from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

APIKeyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    Field(
        description="A human-readable name identifying where the key is used.",
        examples=[
            "local-cli",
            "github-actions",
            "production-worker",
            "mobile-application",
        ],
    ),
]


class APIKeyCreateSchema(BaseModel):
    model_config = ConfigDict(
        title="API Key Creation Request",
        extra="forbid",
    )

    name: APIKeyName


class APIKeyResponseSchema(BaseModel):
    model_config = ConfigDict(
        title="API Key",
        from_attributes=True,
        extra="forbid",
    )

    id: int = Field(json_schema_extra={"readOnly": True})
    name: str = Field(description="The human-readable name assigned when the API key was created.")
    is_active: bool = Field(json_schema_extra={"readOnly": True})
    created_at: datetime = Field(
        description="The creation time as an ISO 8601 timestamp.",
        json_schema_extra={"readOnly": True},
    )


class APIKeyCreatedResponseSchema(APIKeyResponseSchema):
    model_config = ConfigDict(title="API Key Creation Response")

    api_key: str = Field(
        description=(
            "The plaintext API key. It is returned only once and cannot " "be retrieved later."
        ),
        examples=["dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"],
        json_schema_extra={"readOnly": True},
    )
