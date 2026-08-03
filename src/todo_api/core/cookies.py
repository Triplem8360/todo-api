from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import Response

from todo_api.core.config import Settings
from todo_api.core.security import decode_refresh_token
from todo_api.schemas.token import TokenResponseSchema

ACCESS_COOKIE_NAME = "todo_access_token"
REFRESH_COOKIE_NAME = "todo_refresh_token"
CSRF_COOKIE_NAME = "todo_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

API_COOKIE_PATH = "/api/v1"
BROWSER_AUTH_COOKIE_PATH = "/api/v1/auth/browser"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _remaining_seconds(expires_at: datetime) -> int:
    return max(1, int((expires_at - datetime.now(UTC)).total_seconds()))


def set_browser_session_cookies(
    response: Response,
    tokens: TokenResponseSchema,
    settings: Settings,
) -> None:
    """Store a token pair in scoped cookies and issue a CSRF token."""

    refresh_expires_at = decode_refresh_token(tokens.refresh_token, settings).exp
    refresh_max_age = _remaining_seconds(refresh_expires_at)

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        tokens.access_token,
        max_age=tokens.expires_in,
        path=API_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        max_age=refresh_max_age,
        expires=refresh_expires_at,
        path=BROWSER_AUTH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(32),
        max_age=refresh_max_age,
        expires=refresh_expires_at,
        path=API_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite=settings.auth_cookie_samesite,
    )


def clear_browser_session_cookies(response: Response, settings: Settings) -> None:
    """Expire each browser-session cookie using its original attributes."""

    response.delete_cookie(
        ACCESS_COOKIE_NAME,
        path=API_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=BROWSER_AUTH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=API_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite=settings.auth_cookie_samesite,
    )
