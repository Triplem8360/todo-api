from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import hash_secret
from todo_api.exceptions.oauth import (
    InvalidAuthorizationGrantError,
    InvalidOAuthClientError,
    InvalidRedirectURIError,
    InvalidScopeError,
)
from todo_api.models.oauth_authorization_code import OAuthAuthorizationCode
from todo_api.models.user import User
from todo_api.schemas.oauth import (
    OAuthAuthorizationRequestSchema,
    OAuthTokenRequestSchema,
)
from todo_api.schemas.token import TokenResponseSchema
from todo_api.services.auth import AuthService
from todo_api.services.oauth import OAuthService, create_s256_code_challenge

CLIENT_ID = "todo-public-client"
REDIRECT_URI = "http://localhost:8000/docs/oauth2-redirect"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def authorization_request(**changes: str) -> OAuthAuthorizationRequestSchema:
    values = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "client-state",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    values.update(changes)
    return OAuthAuthorizationRequestSchema.model_validate(values)


def token_request(**changes: str) -> OAuthTokenRequestSchema:
    values = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": "authorization-code",
        "code_verifier": VERIFIER,
    }
    values.update(changes)
    return OAuthTokenRequestSchema.model_validate(values)


def oauth_service(settings: Settings) -> tuple[OAuthService, AsyncMock, Mock]:
    session = AsyncMock(spec=AsyncSession)
    auth = Mock(spec=AuthService)
    return OAuthService(session=session, settings=settings, auth=auth), session, auth


def test_s256_challenge_matches_rfc_7636_vector() -> None:
    assert create_s256_code_challenge(VERIFIER) == CHALLENGE


def test_login_session_staging_is_synchronous_and_does_not_commit(settings: Settings) -> None:
    session = AsyncMock(spec=AsyncSession)
    auth = AuthService(session=session, settings=settings)
    user = User(id=7, email="user@example.com", hashed_password="hash", is_active=True)

    tokens = auth.stage_login_session(user)

    assert isinstance(tokens, TokenResponseSchema)
    session.add.assert_called_once()
    session.commit.assert_not_awaited()


def test_authorization_request_requires_registered_client_and_redirect(
    settings: Settings,
) -> None:
    service, _, _ = oauth_service(settings)

    with pytest.raises(InvalidOAuthClientError):
        service.validate_authorization_request(authorization_request(client_id="other-client"))

    with pytest.raises(InvalidRedirectURIError):
        service.validate_authorization_request(
            authorization_request(redirect_uri="https://client.example/callback")
        )

    with pytest.raises(InvalidScopeError):
        service.validate_authorization_request(authorization_request(scope="todos:read"))


def test_authorization_code_is_hashed_and_bound_to_the_request(settings: Settings) -> None:
    service, session, auth = oauth_service(settings)
    user = User(id=7, email="user@example.com", hashed_password="hash", is_active=True)
    auth.authenticate = AsyncMock(return_value=user)

    raw_code = asyncio.run(
        service.issue_authorization_code(
            email=user.email,
            password="correct-password",
            request=authorization_request(),
        )
    )

    record = session.add.call_args.args[0]
    assert isinstance(record, OAuthAuthorizationCode)
    assert record.code_hash == hash_secret(raw_code)
    assert record.code_hash != raw_code
    assert record.user_id == user.id
    assert record.client_id == CLIENT_ID
    assert record.redirect_uri == REDIRECT_URI
    assert record.code_challenge == CHALLENGE
    assert record.consumed_at is None
    assert datetime.now(UTC) < record.expires_at <= datetime.now(UTC) + timedelta(minutes=3)
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_exchange_atomically_consumes_the_code_and_stages_a_session(
    settings: Settings,
) -> None:
    service, session, auth = oauth_service(settings)
    user = User(id=7, email="user@example.com", hashed_password="hash", is_active=True)
    tokens = TokenResponseSchema(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=900,
    )
    session.scalar.return_value = user.id
    session.get.return_value = user
    auth.stage_login_session.return_value = tokens

    exchanged = asyncio.run(service.exchange_authorization_code(token_request()))

    statement = session.scalar.await_args.args[0]
    assert statement.is_update
    assert "consumed_at IS NULL" in str(statement)
    assert "RETURNING oauth_authorization_codes.user_id" in str(statement)
    assert exchanged is tokens
    auth.stage_login_session.assert_called_once()
    session.commit.assert_awaited_once()


def test_exchange_rejects_an_invalid_or_replayed_code(settings: Settings) -> None:
    service, session, auth = oauth_service(settings)
    session.scalar.return_value = None

    with pytest.raises(InvalidAuthorizationGrantError):
        asyncio.run(service.exchange_authorization_code(token_request()))

    auth.stage_login_session.assert_not_called()
    session.commit.assert_not_awaited()
