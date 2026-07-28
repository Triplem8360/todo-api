from __future__ import annotations

from typing import Any

from todo_api.exceptions.base import ApplicationError


def error_response(
    *errors: type[ApplicationError],
    description: str,
    authenticate: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    error.error_code: {
                        "summary": error.public_message,
                        "value": {
                            "detail": error.public_message,
                            "code": error.error_code,
                        },
                    }
                    for error in errors
                }
            }
        },
    }

    if authenticate:
        response["headers"] = {
            "WWW-Authenticate": {
                "description": "Authentication scheme required by the endpoint.",
                "schema": {"type": "string", "example": authenticate},
            }
        }
    return response
