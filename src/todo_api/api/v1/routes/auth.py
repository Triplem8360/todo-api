from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from todo_api.api.deps import AppSettings, DbSession
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
from todo_api.services.auth import (
    authenticate_user,
    create_login_session,
    refresh_login_session,
    register_user,
    revoke_refresh_session,
)

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
async def register(payload: UserCreateSchema, session: DbSession) -> User:
    user = await register_user(session, payload)
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
    settings: AppSettings,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DbSession,
) -> TokenResponseSchema:
    try:
        user = await authenticate_user(session, form.username, form.password)
        tokens = await create_login_session(session, user, settings)
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
            TokenRefreshUnavailableError, 
            description="Token refresh is unavailable."
        ),
    },
)
async def refresh(
    settings: AppSettings,
    payload: RefreshTokenRequestSchema,
    session: DbSession,
) -> TokenResponseSchema:
    try:
        tokens = await refresh_login_session(session, payload.refresh_token, settings)
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
    settings: AppSettings,
    payload: RefreshTokenRequestSchema,
    session: DbSession,
) -> Response:
    await revoke_refresh_session(session, payload.refresh_token, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
