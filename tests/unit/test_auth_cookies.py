from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Response, status
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from todo_api.api.deps import (
    get_current_bearer_user,
    require_browser_csrf_token,
    require_csrf_token,
)
from todo_api.api.v1.routes.auth import (
    browser_login,
    logout_browser_session,
    refresh_browser_session,
)
from todo_api.api.v1.routes.auth import (
    router as auth_router,
)
from todo_api.core.config import Settings
from todo_api.core.cookies import (
    ACCESS_COOKIE_NAME,
    API_COOKIE_PATH,
    BROWSER_AUTH_COOKIE_PATH,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_browser_session_cookies,
    set_browser_session_cookies,
)
from todo_api.core.security import (
    create_token_pair,
    verify_csrf_token,
)
from todo_api.exceptions.auth import (
    InvalidCSRFTokenError,
    InvalidRefreshTokenError,
)
from todo_api.models.user import User
from todo_api.schemas.token import TokenResponseSchema
from todo_api.services.auth import AuthService


def request(
    method: str,
    *,
    path: str = "/api/v1/todos",
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers: list[tuple[bytes, bytes]] = []

    if cookies:
        cookie_value = "; ".join(f"{name}={value}" for name, value in cookies.items())
        raw_headers.append((b"cookie", cookie_value.encode()))

    raw_headers.extend(
        (
            name.lower().encode(),
            value.encode(),
        )
        for name, value in (headers or {}).items()
    )

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
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


def token_pair(
    settings: Settings,
) -> TokenResponseSchema:
    return create_token_pair(
        "1",
        "a" * 64,
        settings,
    )


def cookie_headers(
    response: Response,
) -> dict[str, str]:
    return {header.partition("=")[0]: header for header in response.headers.getlist("set-cookie")}


def auth_service(
    settings: Settings,
) -> Mock:
    service = Mock(spec=AuthService)
    service.settings = settings
    return service


def route_dependencies(
    path: str,
    method: str,
) -> set[object]:
    route = next(
        route
        for route in auth_router.routes
        if (isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods)
    )

    return {dependency.call for dependency in route.dependant.dependencies}


def test_browser_session_cookies_are_scoped_and_hardened(
    settings: Settings,
) -> None:
    secure_settings = settings.model_copy(
        update={
            "auth_cookie_secure": True,
            "auth_cookie_samesite": "strict",
        }
    )
    response = Response()

    set_browser_session_cookies(
        response,
        token_pair(secure_settings),
        secure_settings,
    )

    cookies = cookie_headers(response)

    assert set(cookies) == {
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
    }

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
    with pytest.raises(
        ValidationError,
        match="AUTH_COOKIE_SECURE",
    ):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key=("production-secret-with-enough-" "entropy-1234567890"),
            auth_cookie_secure=False,
        )


def test_clearing_browser_session_uses_original_cookie_paths(
    settings: Settings,
) -> None:
    response = Response()

    clear_browser_session_cookies(
        response,
        settings,
    )

    cookies = cookie_headers(response)

    assert f"Path={API_COOKIE_PATH}" in cookies[ACCESS_COOKIE_NAME]
    assert f"Path={BROWSER_AUTH_COOKIE_PATH}" in cookies[REFRESH_COOKIE_NAME]
    assert f"Path={API_COOKIE_PATH}" in cookies[CSRF_COOKIE_NAME]
    assert all("Max-Age=0" in header for header in cookies.values())


def test_verify_csrf_token_requires_matching_values() -> None:
    assert verify_csrf_token(
        "csrf-value",
        "csrf-value",
    )

    assert not verify_csrf_token(
        "csrf-value",
        "different-value",
    )
    assert not verify_csrf_token(
        None,
        "csrf-value",
    )
    assert not verify_csrf_token(
        "csrf-value",
        None,
    )
    assert not verify_csrf_token(
        "",
        "",
    )


def test_resource_csrf_accepts_matching_cookie_and_header() -> None:
    http_request = request(
        "POST",
        cookies={
            ACCESS_COOKIE_NAME: "access-token",
            CSRF_COOKIE_NAME: "csrf-value",
        },
    )

    require_csrf_token(
        request=http_request,
        csrf_header="csrf-value",
    )


@pytest.mark.parametrize(
    ("csrf_cookie", "csrf_header"),
    [
        ("csrf-value", None),
        (None, "csrf-value"),
        ("csrf-value", "different-value"),
    ],
)
def test_resource_csrf_rejects_missing_or_mismatched_tokens(
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> None:
    cookies = {
        ACCESS_COOKIE_NAME: "access-token",
    }

    if csrf_cookie is not None:
        cookies[CSRF_COOKIE_NAME] = csrf_cookie

    with pytest.raises(InvalidCSRFTokenError):
        require_csrf_token(
            request=request(
                "POST",
                cookies=cookies,
            ),
            csrf_header=csrf_header,
        )


def test_resource_csrf_is_not_required_for_bearer_auth() -> None:
    require_csrf_token(
        request=request(
            "POST",
            cookies={
                ACCESS_COOKIE_NAME: "access-token",
            },
            headers={
                "Authorization": "Bearer bearer-token",
            },
        ),
        csrf_header=None,
    )


def test_resource_csrf_defers_missing_authentication() -> None:
    require_csrf_token(
        request=request("POST"),
        csrf_header=None,
    )


def test_browser_csrf_accepts_refresh_cookie_session() -> None:
    require_browser_csrf_token(
        request=request(
            "POST",
            path="/api/v1/auth/browser/refresh",
            cookies={
                REFRESH_COOKIE_NAME: "refresh-token",
                CSRF_COOKIE_NAME: "csrf-value",
            },
        ),
        csrf_header="csrf-value",
    )


def test_browser_csrf_accepts_access_cookie_session() -> None:
    require_browser_csrf_token(
        request=request(
            "POST",
            path="/api/v1/auth/browser/logout",
            cookies={
                ACCESS_COOKIE_NAME: "access-token",
                CSRF_COOKIE_NAME: "csrf-value",
            },
        ),
        csrf_header="csrf-value",
    )


@pytest.mark.parametrize(
    ("csrf_cookie", "csrf_header"),
    [
        ("csrf-value", None),
        (None, "csrf-value"),
        ("csrf-value", "different-value"),
    ],
)
def test_browser_csrf_rejects_missing_or_mismatched_tokens(
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> None:
    cookies = {
        REFRESH_COOKIE_NAME: "refresh-token",
    }

    if csrf_cookie is not None:
        cookies[CSRF_COOKIE_NAME] = csrf_cookie

    with pytest.raises(InvalidCSRFTokenError):
        require_browser_csrf_token(
            request=request(
                "POST",
                path="/api/v1/auth/browser/refresh",
                cookies=cookies,
            ),
            csrf_header=csrf_header,
        )


def test_browser_csrf_defers_missing_browser_session() -> None:
    require_browser_csrf_token(
        request=request(
            "POST",
            path="/api/v1/auth/browser/logout",
        ),
        csrf_header=None,
    )


def test_browser_auth_routes_use_csrf_dependency() -> None:
    assert require_browser_csrf_token in route_dependencies(
        "/auth/browser/refresh",
        "POST",
    )
    assert require_browser_csrf_token in route_dependencies(
        "/auth/browser/logout",
        "POST",
    )
    assert require_browser_csrf_token not in route_dependencies(
        "/auth/browser/login",
        "POST",
    )


def test_access_cookie_authenticates_without_csrf_side_effects(
    settings: Settings,
) -> None:
    tokens = token_pair(settings)
    user = active_user()
    session = AsyncMock(spec=AsyncSession)

    get_user = AsyncMock(return_value=user)

    with patch(
        "todo_api.api.deps.get_user_by_id",
        get_user,
    ):
        authenticated = asyncio.run(
            get_current_bearer_user(
                settings=settings,
                credentials=None,
                cookie_token=tokens.access_token,
                session=session,
            )
        )

    get_user.assert_awaited_once_with(
        session,
        user.id,
    )
    assert authenticated is user


def test_bearer_header_takes_precedence_over_cookie(
    settings: Settings,
) -> None:
    tokens = token_pair(settings)
    user = active_user()
    session = AsyncMock(spec=AsyncSession)

    get_user = AsyncMock(return_value=user)

    with patch(
        "todo_api.api.deps.get_user_by_id",
        get_user,
    ):
        authenticated = asyncio.run(
            get_current_bearer_user(
                settings=settings,
                credentials=HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=tokens.access_token,
                ),
                cookie_token="invalid-cookie-token",
                session=session,
            )
        )

    assert authenticated is user


def test_browser_login_sets_cookies_without_returning_tokens(
    settings: Settings,
) -> None:
    tokens = token_pair(settings)
    service = auth_service(settings)
    service.authenticate = AsyncMock(return_value=active_user())
    service.create_login_session = AsyncMock(return_value=tokens)
    response = Response()

    result = asyncio.run(
        browser_login(
            response=response,
            service=service,
            form=SimpleNamespace(
                username="user@example.com",
                password="password",
            ),
        )
    )

    assert result.model_dump() == {
        "authenticated": True,
        "expires_in": tokens.expires_in,
    }
    assert set(cookie_headers(response)) == {
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_browser_refresh_rotates_cookies(
    settings: Settings,
) -> None:
    tokens = token_pair(settings)
    service = auth_service(settings)
    service.refresh_login_session = AsyncMock(return_value=tokens)
    response = Response()

    result = asyncio.run(
        refresh_browser_session(
            request=request(
                "POST",
                path="/api/v1/auth/browser/refresh",
                cookies={
                    REFRESH_COOKIE_NAME: ("presented-refresh-token"),
                },
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
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_browser_refresh_requires_refresh_cookie(
    settings: Settings,
) -> None:
    service = auth_service(settings)
    service.refresh_login_session = AsyncMock()
    response = Response()

    with pytest.raises(InvalidRefreshTokenError):
        asyncio.run(
            refresh_browser_session(
                request=request(
                    "POST",
                    path="/api/v1/auth/browser/refresh",
                ),
                response=response,
                service=service,
            )
        )

    service.refresh_login_session.assert_not_awaited()


def test_browser_logout_revokes_and_clears_cookies(
    settings: Settings,
) -> None:
    service = auth_service(settings)
    service.revoke_refresh_session = AsyncMock()

    response = asyncio.run(
        logout_browser_session(
            request=request(
                "POST",
                path="/api/v1/auth/browser/logout",
                cookies={
                    REFRESH_COOKIE_NAME: ("presented-refresh-token"),
                },
            ),
            service=service,
        )
    )

    service.revoke_refresh_session.assert_awaited_once_with("presented-refresh-token")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert all("Max-Age=0" in header for header in cookie_headers(response).values())


def test_browser_logout_without_refresh_cookie_is_idempotent(
    settings: Settings,
) -> None:
    service = auth_service(settings)
    service.revoke_refresh_session = AsyncMock()

    response = asyncio.run(
        logout_browser_session(
            request=request(
                "POST",
                path="/api/v1/auth/browser/logout",
            ),
            service=service,
        )
    )

    service.revoke_refresh_session.assert_not_awaited()
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert set(cookie_headers(response)) == {
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
    }
