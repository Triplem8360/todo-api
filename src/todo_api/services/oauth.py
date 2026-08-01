from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import hash_secret
from todo_api.exceptions.auth import LoginSessionUnavailableError
from todo_api.exceptions.oauth import (
    AuthorizationCodeExchangeUnavailableError,
    AuthorizationCodeIssuanceUnavailableError,
    InvalidAuthorizationGrantError,
    InvalidOAuthClientError,
    InvalidRedirectURIError,
    InvalidScopeError,
)
from todo_api.repositories.oauth import (
    consume_authorization_code,
    create_authorization_code,
    prune_expired_authorization_codes,
)
from todo_api.repositories.user import get_user_by_id
from todo_api.schemas.oauth import (
    OAuthAuthorizationRequestSchema,
    OAuthTokenRequestSchema,
)
from todo_api.schemas.token import TokenResponseSchema
from todo_api.services.auth import AuthService


def create_s256_code_challenge(code_verifier: str) -> str:
    """Create the RFC 7636 S256 challenge for a PKCE verifier."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(slots=True)
class OAuthService:
    """Authorization Code + mandatory PKCE/S256 use cases.

    This implementation supports one configured first-party public client.
    Existing password/refresh/logout flows remain separate.
    """

    session: AsyncSession
    settings: Settings
    auth: AuthService

    def validate_authorization_request(self, request: OAuthAuthorizationRequestSchema) -> None:
        if request.client_id != self.settings.oauth2_public_client_id:
            raise InvalidOAuthClientError()

        if request.redirect_uri not in self.settings.oauth2_redirect_uris:
            raise InvalidRedirectURIError()

        if request.scope.strip():
            raise InvalidScopeError()

    async def issue_authorization_code(
        self,
        *,
        email: str,
        password: str,
        request: OAuthAuthorizationRequestSchema,
    ) -> str:
        """Authenticate the user and persist a hashed, short-lived code."""

        self.validate_authorization_request(request)
        
        try:
            user = await self.auth.authenticate(email, password)
        except LoginSessionUnavailableError as exc:
            raise AuthorizationCodeIssuanceUnavailableError() from exc

        raw_code = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.settings.oauth2_authorization_code_ttl_seconds)

        try:
            await prune_expired_authorization_codes(
                self.session,
                expired_at=now,
            )
            
            await create_authorization_code(
                self.session,
                code_hash=hash_secret(raw_code),
                user_id=user.id,
                client_id=request.client_id,
                redirect_uri=request.redirect_uri,
                code_challenge=request.code_challenge,
                expires_at=expires_at,
            )
            
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise AuthorizationCodeIssuanceUnavailableError() from exc

        return raw_code

    async def exchange_authorization_code(
        self,
        request: OAuthTokenRequestSchema,
    ) -> TokenResponseSchema:
        """Atomically consume an authorization code and create a session."""

        if request.client_id != self.settings.oauth2_public_client_id:
            raise InvalidOAuthClientError()

        now = datetime.now(UTC)
        code_hash = hash_secret(request.code)
        presented_challenge = create_s256_code_challenge(
            request.code_verifier,
        )

        try:
            user_id = await consume_authorization_code(
                self.session,
                code_hash=code_hash,
                client_id=request.client_id,
                redirect_uri=request.redirect_uri,
                code_challenge=presented_challenge,
                consumed_at=now,
            )

            if user_id is None:
                raise InvalidAuthorizationGrantError()

            user = await get_user_by_id(self.session, user_id)

            if user is None or not user.is_active:
                raise InvalidAuthorizationGrantError()

            tokens = self.auth.stage_login_session(user, issued_at=now)
            await self.session.commit()
        except InvalidAuthorizationGrantError:
            raise
        except SQLAlchemyError as exc:
            raise AuthorizationCodeExchangeUnavailableError() from exc

        return tokens
