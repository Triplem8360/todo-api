from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from todo_api.api.deps import AuthServiceDep, require_browser_csrf_token
from todo_api.api.responses import error_response
from todo_api.background.request_tasks import record_activity
from todo_api.core.cookies import (
    REFRESH_COOKIE_NAME,
    clear_browser_session_cookies,
    set_browser_session_cookies,
)
from todo_api.exceptions.auth import (
    AuthServiceError,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidCSRFTokenError,
    InvalidRefreshTokenError,
    LoginSessionUnavailableError,
    LogoutUnavailableError,
    RegistrationUnavailableError,
    TokenRefreshUnavailableError,
)
from todo_api.models.user import User
from todo_api.observability.metrics import record_auth_attempt, record_registration
from todo_api.schemas.token import (
    BrowserSessionResponseSchema,
    RefreshTokenRequestSchema,
    TokenResponseSchema,
)
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
    background_tasks: BackgroundTasks,
) -> User:
    user = await service.register(payload)
    record_registration("success")
    background_tasks.add_task(
        record_activity,
        "user.registered",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
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
    "/browser/login",
    response_model=BrowserSessionResponseSchema,
    summary="Create a browser cookie session",
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
async def browser_login(
    response: Response,
    service: AuthServiceDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> BrowserSessionResponseSchema:
    """Create HttpOnly access/refresh cookies without exposing tokens in JSON."""

    try:
        user = await service.authenticate(form.username, form.password)
        tokens = await service.create_login_session(user)
    except AuthServiceError as exc:
        record_auth_attempt("password_cookie", _authentication_failure_outcome(exc))
        raise

    set_browser_session_cookies(response, tokens, service.settings)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    record_auth_attempt("password_cookie", "success")
    return BrowserSessionResponseSchema(expires_in=tokens.expires_in)


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
    "/browser/refresh",
    response_model=BrowserSessionResponseSchema,
    summary="Rotate a browser cookie session",
    responses={
        status.HTTP_401_UNAUTHORIZED: error_response(
            InvalidRefreshTokenError,
            description="Refresh cookie is invalid.",
            authenticate="Bearer",
        ),
        status.HTTP_403_FORBIDDEN: error_response(
            InactiveUserError,
            InvalidCSRFTokenError,
            description="Account is inactive or the CSRF token is invalid.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            TokenRefreshUnavailableError,
            description="Token refresh is unavailable.",
        ),
    },
    dependencies=[Depends(require_browser_csrf_token)],
)
async def refresh_browser_session(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> BrowserSessionResponseSchema:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise InvalidRefreshTokenError()

    try:
        tokens = await service.refresh_login_session(refresh_token)
    except AuthServiceError as exc:
        record_auth_attempt("refresh_cookie", _authentication_failure_outcome(exc))
        raise

    set_browser_session_cookies(response, tokens, service.settings)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    record_auth_attempt("refresh_cookie", "success")
    return BrowserSessionResponseSchema(expires_in=tokens.expires_in)


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


@router.post(
    "/browser/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a browser cookie session",
    responses={
        status.HTTP_403_FORBIDDEN: error_response(
            InvalidCSRFTokenError,
            description="CSRF token is invalid.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            LogoutUnavailableError,
            description="Logout is unavailable.",
        ),
    },
    dependencies=[Depends(require_browser_csrf_token)],
)
async def logout_browser_session(
    request: Request,
    service: AuthServiceDep,
) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        await service.revoke_refresh_session(refresh_token)

    response = Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    clear_browser_session_cookies(response, service.settings)
    return response
