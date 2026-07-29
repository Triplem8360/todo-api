from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from todo_api.api.deps import AuthServiceDep
from todo_api.api.responses import error_response
from todo_api.exceptions.auth import (
    AuthServiceError,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginSessionUnavailableError,
    LogoutUnavailableError,
    RegistrationUnavailableError,
    TokenRefreshUnavailableError,
)
from todo_api.models.user import User
from todo_api.observability.metrics import record_auth_attempt, record_registration
from todo_api.schemas.token import RefreshTokenRequestSchema, TokenResponseSchema
from todo_api.schemas.user import UserCreateSchema, UserResponseSchema

router = APIRouter(prefix="/auth", tags=["Auth"])


def _authentication_failure_outcome(error: AuthServiceError) -> str:
    if isinstance(error, InactiveUserError):
        return "inactive"
    if isinstance(error, (InvalidCredentialsError, InvalidRefreshTokenError)):
        return "invalid"
    return "error"


@router.post(
    "/register",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: error_response(
            EmailAlreadyRegisteredError,
            description="Email already registered.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            RegistrationUnavailableError, description="Registration is unavailable."
        ),
    },
)
async def register(
    payload: UserCreateSchema,
    service: AuthServiceDep,
) -> User:
    user = await service.register(payload)
    record_registration("success")
    return user


@router.post(
    "/login",
    response_model=TokenResponseSchema,
    responses={
        status.HTTP_401_UNAUTHORIZED: error_response(
            InvalidCredentialsError,
            description="Credentials are invalid.",
            authenticate="Bearer",
        ),
        status.HTTP_403_FORBIDDEN: error_response(
            InactiveUserError,
            description="Account is inactive.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            LoginSessionUnavailableError,
            description="Login is unavailable.",
        ),
    },
)
async def login(
    service: AuthServiceDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponseSchema:
    try:
        user = await service.authenticate(form.username, form.password)
        tokens = await service.create_login_session(user)
    except AuthServiceError as exc:
        record_auth_attempt("password", _authentication_failure_outcome(exc))
        raise

    record_auth_attempt("password", "success")
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponseSchema,
    responses={
        status.HTTP_401_UNAUTHORIZED: error_response(
            InvalidRefreshTokenError,
            description="Refresh token is invalid.",
            authenticate="Bearer",
        ),
        status.HTTP_403_FORBIDDEN: error_response(
            InactiveUserError,
            description="Account is inactive.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            TokenRefreshUnavailableError, description="Token refresh is unavailable."
        ),
    },
)
async def refresh(
    payload: RefreshTokenRequestSchema,
    service: AuthServiceDep,
) -> TokenResponseSchema:
    try:
        tokens = await service.refresh_login_session(payload.refresh_token)
    except AuthServiceError as exc:
        record_auth_attempt("refresh", _authentication_failure_outcome(exc))
        raise

    record_auth_attempt("refresh", "success")
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            LogoutUnavailableError,
            description="Logout is unavailable.",
        )
    },
)
async def logout(
    payload: RefreshTokenRequestSchema,
    service: AuthServiceDep,
) -> Response:
    await service.revoke_refresh_session(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
