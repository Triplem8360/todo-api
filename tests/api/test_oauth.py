from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.requests import Request

from todo_api.api.exception_handlers import oauth_error_handler
from todo_api.api.v1.routes.oauth import (
    _login_page,
    _redirect_authorization_error,
    _token_request,
    authorize,
)
from todo_api.core.config import Settings
from todo_api.exceptions.oauth import (
    InvalidAuthorizationGrantError,
    InvalidOAuthClientError,
    UnsupportedResponseTypeError,
)
from todo_api.schemas.oauth import OAuthAuthorizationRequestSchema
from todo_api.services.oauth import OAuthService

CHALLENGE = "A" * 43


def oauth_service(settings: Settings) -> Mock:
    service = Mock(spec=OAuthService)
    service.settings = settings
    return service


def authorization_parameters(settings: Settings) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": settings.oauth2_public_client_id,
        "redirect_uri": settings.oauth2_redirect_uris[0],
        "state": "client-state",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }


def test_authorization_page_has_security_and_no_store_headers(settings: Settings) -> None:
    request = OAuthAuthorizationRequestSchema.model_validate(authorization_parameters(settings))

    response = _login_page(request)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_authorization_error_redirects_only_to_registered_uri(settings: Settings) -> None:
    service = oauth_service(settings)
    parameters = authorization_parameters(settings)

    response = _redirect_authorization_error(
        service,
        UnsupportedResponseTypeError(),
        client_id=parameters["client_id"],
        redirect_uri=parameters["redirect_uri"],
        state=parameters["state"],
    )

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert response.status_code == 302
    assert query["error"] == ["unsupported_response_type"]
    assert query["state"] == [parameters["state"]]

    with pytest.raises(UnsupportedResponseTypeError):
        _redirect_authorization_error(
            service,
            UnsupportedResponseTypeError(),
            client_id=parameters["client_id"],
            redirect_uri="https://attacker.example/callback",
            state=parameters["state"],
        )


def test_authorization_code_response_uses_post_redirect_get(settings: Settings) -> None:
    service = oauth_service(settings)
    service.issue_authorization_code = AsyncMock(return_value="raw-code")
    parameters = authorization_parameters(settings)

    response = asyncio.run(
        authorize(
            oauth=service,
            email="user@example.com",
            password="correct-password",
            **parameters,
        )
    )

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert response.status_code == 303
    assert query == {"code": ["raw-code"], "state": [parameters["state"]]}


def test_token_errors_use_oauth_json_and_no_store_headers(settings: Settings) -> None:
    with pytest.raises(InvalidAuthorizationGrantError) as raised:
        _token_request(
            grant_type="authorization_code",
            code="raw-code",
            client_id=settings.oauth2_public_client_id,
            redirect_uri=settings.oauth2_redirect_uris[0],
            code_verifier="too-short",
        )

    request = Request({"type": "http", "path": "/api/v1/auth/token", "headers": []})
    response = asyncio.run(oauth_error_handler(request, raised.value))

    assert response.status_code == 400
    assert b'"error":"invalid_grant"' in response.body
    assert response.headers["cache-control"] == "no-store"


def test_token_endpoint_rejects_attempted_client_authentication() -> None:
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/auth/token",
            "headers": [(b"authorization", b"Basic invalid")],
        }
    )

    response = asyncio.run(oauth_error_handler(request, InvalidOAuthClientError()))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="oauth-token"'
