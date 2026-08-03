from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from todo_api.api.deps import get_current_bearer_user
from todo_api.api.v1.routes.auth import (
    browser_login,
    logout_browser_session,
    refresh_browser_session,
)
from todo_api.core.config import Settings
from todo_api.core.cookies import (
    ACCESS_COOKIE_NAME,
    API_COOKIE_PATH,
    BROWSER_AUTH_COOKIE_PATH,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    REFRESH_COOKIE_NAME,
    clear_browser_session_cookies,
    set_browser_session_cookies,
    validate_cookie_csrf,
)
from todo_api.core.security import create_token_pair
from todo_api.exceptions.auth import InvalidCSRFTokenError
from todo_api.models.user import User
from todo_api.schemas.token import TokenResponseSchema
from todo_api.services.auth import AuthService


def request(
    method: str,
    *,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = []
    if cookies:
        cookie_value = "; ".join(f"{name}={value}" for name, value in cookies.items())
        raw_headers.append((b"cookie", cookie_value.encode()))
    raw_headers.extend(
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    )
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/todos",
            "headers": raw_headers,
        }
    )


def active_user() -> User:
    return User(
        id=1,
        email="user@example.com",
        hashed_password="password-hash",
        is_active=True,
        is_superuser=False,
    )


def token_pair(settings: Settings) -> TokenResponseSchema:
    return create_token_pair("1", "a" * 64, settings)


def cookie_headers(response: Response) -> dict[str, str]:
    return {header.partition("=")[0]: header for header in response.headers.getlist("set-cookie")}


def test_browser_session_cookies_are_scoped_and_hardened(settings: Settings) -> None:
    secure_settings = settings.model_copy(
        update={"auth_cookie_secure": True, "auth_cookie_samesite": "strict"}
    )
    response = Response()

    set_browser_session_cookies(response, token_pair(secure_settings), secure_settings)

    cookies = cookie_headers(response)
    assert set(cookies) == {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME}

    assert f"Path={API_COOKIE_PATH}" in cookies[ACCESS_COOKIE_NAME]
    assert "HttpOnly" in cookies[ACCESS_COOKIE_NAME]
    assert f"Path={BROWSER_AUTH_COOKIE_PATH}" in cookies[REFRESH_COOKIE_NAME]
    assert "HttpOnly" in cookies[REFRESH_COOKIE_NAME]
    assert f"Path={API_COOKIE_PATH}" in cookies[CSRF_COOKIE_NAME]
    assert "HttpOnly" not in cookies[CSRF_COOKIE_NAME]

    for header in cookies.values():
        assert "Max-Age=" in header
        assert "SameSite=strict" in header
        assert "Secure" in header


def test_deployed_environments_require_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="production-secret-with-enough-entropy-1234567890",
            auth_cookie_secure=False,
        )


def test_clearing_browser_session_uses_the_original_cookie_paths(settings: Settings) -> None:
    response = Response()

    clear_browser_session_cookies(response, settings)

    cookies = cookie_headers(response)
    assert f"Path={API_COOKIE_PATH}" in cookies[ACCESS_COOKIE_NAME]
    assert f"Path={BROWSER_AUTH_COOKIE_PATH}" in cookies[REFRESH_COOKIE_NAME]
    assert f"Path={API_COOKIE_PATH}" in cookies[CSRF_COOKIE_NAME]
    assert all("Max-Age=0" in header for header in cookies.values())


def test_cookie_csrf_requires_matching_cookie_and_header() -> None:
    valid_request = request(
        "POST",
        cookies={CSRF_COOKIE_NAME: "csrf-value"},
        headers={CSRF_HEADER_NAME: "csrf-value"},
    )
    validate_cookie_csrf(valid_request)

    with pytest.raises(InvalidCSRFTokenError):
        validate_cookie_csrf(
            request(
                "POST",
                cookies={CSRF_COOKIE_NAME: "csrf-value"},
                headers={CSRF_HEADER_NAME: "different-value"},
            )
        )

    validate_cookie_csrf(request("GET"))


def test_access_cookie_authenticates_and_enforces_csrf(settings: Settings) -> None:
    tokens = token_pair(settings)
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = user

    authenticated = asyncio.run(
        get_current_bearer_user(
            settings=settings,
            request=request(
                "POST",
                cookies={CSRF_COOKIE_NAME: "csrf-value"},
                headers={CSRF_HEADER_NAME: "csrf-value"},
            ),
            credentials=None,
            cookie_token=tokens.access_token,
            session=session,
        )
    )
    assert authenticated is user

    with pytest.raises(InvalidCSRFTokenError):
        asyncio.run(
            get_current_bearer_user(
                settings=settings,
                request=request("POST"),
                credentials=None,
                cookie_token=tokens.access_token,
                session=session,
            )
        )


def test_bearer_header_takes_precedence_without_csrf(settings: Settings) -> None:
    tokens = token_pair(settings)
    user = active_user()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = user

    authenticated = asyncio.run(
        get_current_bearer_user(
            settings=settings,
            request=request("POST"),
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=tokens.access_token,
            ),
            cookie_token=None,
            session=session,
        )
    )
    assert authenticated is user


def auth_service(settings: Settings) -> Mock:
    service = Mock(spec=AuthService)
    service.settings = settings
    return service


def test_browser_login_sets_cookies_without_returning_tokens(settings: Settings) -> None:
    tokens = token_pair(settings)
    service = auth_service(settings)
    service.authenticate = AsyncMock(return_value=active_user())
    service.create_login_session = AsyncMock(return_value=tokens)
    response = Response()

    result = asyncio.run(
        browser_login(
            response=response,
            service=service,
            form=SimpleNamespace(username="user@example.com", password="password"),
        )
    )

    assert result.model_dump() == {"authenticated": True, "expires_in": tokens.expires_in}
    assert set(cookie_headers(response)) == {
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
    }
    assert response.headers["cache-control"] == "no-store"


def test_browser_refresh_rotates_cookies(settings: Settings) -> None:
    tokens = token_pair(settings)
    service = auth_service(settings)
    service.refresh_login_session = AsyncMock(return_value=tokens)
    response = Response()

    result = asyncio.run(
        refresh_browser_session(
            request=request(
                "POST",
                cookies={
                    REFRESH_COOKIE_NAME: "presented-refresh-token",
                    CSRF_COOKIE_NAME: "csrf-value",
                },
                headers={CSRF_HEADER_NAME: "csrf-value"},
            ),
            response=response,
            service=service,
        )
    )

    service.refresh_login_session.assert_awaited_once_with("presented-refresh-token")
    assert result.expires_in == tokens.expires_in
    assert set(cookie_headers(response)) == {
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
    }


def test_browser_logout_revokes_and_clears_cookies(settings: Settings) -> None:
    service = auth_service(settings)
    service.revoke_refresh_session = AsyncMock()

    response = asyncio.run(
        logout_browser_session(
            request=request(
                "POST",
                cookies={
                    REFRESH_COOKIE_NAME: "presented-refresh-token",
                    CSRF_COOKIE_NAME: "csrf-value",
                },
                headers={CSRF_HEADER_NAME: "csrf-value"},
            ),
            service=service,
        )
    )

    service.revoke_refresh_session.assert_awaited_once_with("presented-refresh-token")
    assert response.status_code == 204
    assert all("Max-Age=0" in header for header in cookie_headers(response).values())


def test_browser_logout_requires_csrf_even_without_a_refresh_cookie(
    settings: Settings,
) -> None:
    service = auth_service(settings)
    service.revoke_refresh_session = AsyncMock()

    with pytest.raises(InvalidCSRFTokenError):
        asyncio.run(
            logout_browser_session(
                request=request("POST"),
                service=service,
            )
        )

    service.revoke_refresh_session.assert_not_awaited()
