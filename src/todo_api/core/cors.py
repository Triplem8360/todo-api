from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from todo_api.core.config import Settings
from todo_api.core.cookies import CSRF_HEADER_NAME
from todo_api.observability.request_context import (
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
)

_ALLOWED_METHODS = [
    "GET",
    "POST",
    "PATCH",
    "DELETE",
]

_ALLOWED_HEADERS = [
    "Accept",
    "Authorization",
    "Content-Type",
    CSRF_HEADER_NAME,
    REQUEST_ID_HEADER,
]

_EXPOSED_HEADERS = [
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
]


def register_cors_middleware(
    app: FastAPI,
    *,
    settings: Settings,
) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
        expose_headers=_EXPOSED_HEADERS,
        max_age=settings.cors_max_age_seconds,
        allow_private_network=False,
    )
