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
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RegistrationUnavailableError,
)
from todo_api.exceptions.base import ApplicationError
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

    if config.status_code >= 500:
        logger.error(
            "Application operation failed",
            extra={
                "error_code": exception.error_code,
                "exception_type": type(exception).__name__,
            },
            exc_info=(type(exception), exception, exception.__traceback__),
        )

    headers = {"WWW-Authenticate": config.authenticate} if config.authenticate else None

    return JSONResponse(
        status_code=config.status_code,
        content={"detail": exception.public_message, "code": exception.error_code},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)
