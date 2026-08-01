from __future__ import annotations

from typing import ClassVar

from todo_api.exceptions.base import ApplicationError


class OAuthServiceError(ApplicationError):
    """Base error for OAuth authorization-server operations."""

    error_code = "oauth_service_error"
    public_message = "OAuth operation failed."

    oauth_error: ClassVar[str] = "server_error"


class OAuthProtocolError(OAuthServiceError):
    """Base error that can be serialized as an OAuth protocol response."""

    error_code = "oauth_protocol_error"
    public_message = "The authorization server could not process the request."


class InvalidAuthorizationRequestError(OAuthProtocolError):
    error_code = "invalid_authorization_request"
    public_message = "The authorization request is invalid."

    oauth_error = "invalid_request"


class UnsupportedResponseTypeError(OAuthProtocolError):
    error_code = "unsupported_response_type"
    public_message = "Only response_type=code is supported."

    oauth_error = "unsupported_response_type"


class InvalidOAuthClientError(OAuthProtocolError):
    error_code = "invalid_oauth_client"
    public_message = "The OAuth client is invalid."

    oauth_error = "invalid_client"


class InvalidRedirectURIError(OAuthProtocolError):
    error_code = "invalid_redirect_uri"
    public_message = "The redirect_uri is not registered for this client."

    oauth_error = "invalid_request"


class UnsupportedCodeChallengeMethodError(OAuthProtocolError):
    error_code = "unsupported_code_challenge_method"
    public_message = "Only the S256 PKCE code challenge method is supported."

    oauth_error = "invalid_request"


class InvalidCodeChallengeError(OAuthProtocolError):
    error_code = "invalid_code_challenge"
    public_message = "The PKCE code_challenge is invalid."

    oauth_error = "invalid_request"


class InvalidScopeError(OAuthProtocolError):
    error_code = "invalid_oauth_scope"
    public_message = "The requested OAuth scope is not supported."

    oauth_error = "invalid_scope"


class UnsupportedGrantTypeError(OAuthProtocolError):
    error_code = "unsupported_grant_type"
    public_message = "Only grant_type=authorization_code is supported."

    oauth_error = "unsupported_grant_type"


class InvalidAuthorizationGrantError(OAuthProtocolError):
    error_code = "invalid_authorization_grant"
    public_message = "The authorization code or PKCE verifier is invalid."

    oauth_error = "invalid_grant"


class AuthorizationCodeIssuanceUnavailableError(OAuthServiceError):
    error_code = "authorization_code_issuance_unavailable"
    public_message = "The authorization code could not be issued."


class AuthorizationCodeExchangeUnavailableError(OAuthServiceError):
    error_code = "authorization_code_exchange_unavailable"
    public_message = "The authorization code could not be exchanged."
