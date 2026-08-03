from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from todo_api.exceptions.api_key import (
    APIKeyNotFoundError,
    APIKeyRequiredError,
    APIKeyServiceError,
    InvalidAPIKeyError,
)
from todo_api.exceptions.auth import (
    AuthServiceError,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidBasicCredentialsError,
    InvalidCSRFTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RegistrationUnavailableError,
)
from todo_api.exceptions.base import ApplicationError
from todo_api.exceptions.oauth import (
    InvalidOAuthClientError,
    OAuthProtocolError,
    OAuthServiceError,
)
from todo_api.exceptions.user import UserServiceError
from todo_api.observability.metrics import record_registration

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErrorConfig:
    status_code: int
    authenticate: str | None = None


ERROR_CONFIG: dict[type[ApplicationError], ErrorConfig] = {
    EmailAlreadyRegisteredError: ErrorConfig(status.HTTP_409_CONFLICT),
    InvalidCredentialsError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "Bearer"),
    InvalidBasicCredentialsError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "Basic"),
    InvalidAccessTokenError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "Bearer"),
    InvalidRefreshTokenError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "Bearer"),
    InvalidCSRFTokenError: ErrorConfig(status.HTTP_403_FORBIDDEN),
    APIKeyRequiredError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "APIKey"),
    InvalidAPIKeyError: ErrorConfig(status.HTTP_401_UNAUTHORIZED, "APIKey"),
    InactiveUserError: ErrorConfig(status.HTTP_403_FORBIDDEN),
    APIKeyNotFoundError: ErrorConfig(status.HTTP_404_NOT_FOUND),
    AuthServiceError: ErrorConfig(status.HTTP_503_SERVICE_UNAVAILABLE),
    APIKeyServiceError: ErrorConfig(status.HTTP_503_SERVICE_UNAVAILABLE),
    UserServiceError: ErrorConfig(status.HTTP_503_SERVICE_UNAVAILABLE),
}


def _config_for(error: ApplicationError) -> ErrorConfig:
    for error_type in type(error).__mro__:
        if config := ERROR_CONFIG.get(error_type):
            return config

    return ErrorConfig(status.HTTP_500_INTERNAL_SERVER_ERROR)


def _log_server_error(exception: ApplicationError, status_code: int) -> None:
    if status_code >= 500:
        logger.error(
            "Application operation failed",
            extra={
                "error_code": exception.error_code,
                "exception_type": type(exception).__name__,
            },
            exc_info=(type(exception), exception, exception.__traceback__),
        )


async def oauth_error_handler(
    request: Request,
    exception: OAuthServiceError,
) -> JSONResponse:
    attempted_client_authentication = bool(request.headers.get("Authorization"))

    status_code = (
        status.HTTP_400_BAD_REQUEST
        if isinstance(exception, OAuthProtocolError)
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    }

    if (
        isinstance(exception, InvalidOAuthClientError)
        and request.url.path.endswith("/token")
        and attempted_client_authentication
    ):
        status_code = status.HTTP_401_UNAUTHORIZED
        headers["WWW-Authenticate"] = 'Basic realm="oauth-token"'

    _log_server_error(exception, status_code)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": exception.oauth_error,
            "error_description": exception.public_message,
        },
        headers=headers,
    )


async def application_error_handler(
    request: Request,
    exception: ApplicationError,
) -> JSONResponse:
    del request

    config = _config_for(exception)

    if isinstance(exception, EmailAlreadyRegisteredError):
        record_registration("conflict")
    elif isinstance(exception, RegistrationUnavailableError):
        record_registration("error")

    _log_server_error(exception, config.status_code)

    headers = {"WWW-Authenticate": config.authenticate} if config.authenticate else None

    return JSONResponse(
        status_code=config.status_code,
        content={
            "detail": exception.public_message,
            "code": exception.error_code,
        },
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(OAuthServiceError, oauth_error_handler)
    app.add_exception_handler(ApplicationError, application_error_handler)
