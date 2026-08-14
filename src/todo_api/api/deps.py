from __future__ import annotations

from typing import Annotated, TypeAlias
from urllib.parse import urlsplit

from anyio import to_thread
from fastapi import Depends, Request, Security
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordBearer,
)
from pwdlib.exceptions import UnknownHashError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.cookies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    SAFE_METHODS,
)
from todo_api.core.security import (
    API_KEY_HEADER,
    CSRF_TOKEN_HEADER,
    DUMMY_PASSWORD_HASH,
    decode_access_token,
    hash_secret,
    verify_csrf_token,
    verify_password,
)
from todo_api.db.session import get_session
from todo_api.exceptions.api_key import (
    APIKeyRequiredError,
    APIKeyServiceError,
    InvalidAPIKeyError,
)
from todo_api.exceptions.auth import (
    BasicAuthenticationUnavailableError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidBasicCredentialsError,
    InvalidCSRFTokenError,
    RequestOriginNotAllowedError,
    TokenAuthenticationUnavailableError,
)
from todo_api.models.user import User
from todo_api.observability.metrics import record_auth_attempt
from todo_api.repositories.api_key import get_active_api_key_by_hash
from todo_api.repositories.user import get_user_by_email, get_user_by_id
from todo_api.services.api_key import APIKeyService
from todo_api.services.auth import AuthService
from todo_api.services.email import EmailService
from todo_api.services.oauth import OAuthService
from todo_api.services.todo import TodoService
from todo_api.services.user import UserService
from todo_api.utils.email import normalize_email

ACCESS_TOKEN_AUTH = "access_token"
BASIC_AUTH = "basic"
HEADER_API_KEY_AUTH = "api_key_header"
QUERY_API_KEY_AUTH = "api_key_query"

_BROWSER_SESSION_COOKIE_NAMES = (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
)


# Security transports.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scheme_name="OAuth2PasswordBearer",
    auto_error=False,
)
oauth2_password_scheme = oauth2_scheme
oauth2_authorization_code_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="/api/v1/auth/authorize",
    tokenUrl="/api/v1/auth/token",
    scheme_name="OAuth2AuthorizationCodeBearer",
    auto_error=False,
)
bearer_schema = HTTPBearer(
    scheme_name="HTTPBearer",
    auto_error=False,
)
access_cookie_scheme = APIKeyCookie(
    name=ACCESS_COOKIE_NAME,
    scheme_name="BrowserAccessCookie",
    description=(
        "Browser-managed HttpOnly access cookie issued by "
        "POST /api/v1/auth/browser/login. Do not paste a value "
        "into Swagger; the browser sends this cookie automatically."
    ),
    auto_error=False,
)
basic_scheme = HTTPBasic(scheme_name="BasicAuth", auto_error=False)
api_key_header_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    scheme_name="APIKeyHeaderAuth",
    description="API key returned once by POST /api/v1/api-keys.",
    auto_error=False,
)
api_key_query_scheme = APIKeyQuery(
    name="api_key",
    scheme_name="APIKeyQueryAuth",
    description="Compatibility-only transport; prefer the X-API-Key header.",
    auto_error=False,
)
csrf_header_scheme = APIKeyHeader(
    name=CSRF_TOKEN_HEADER,
    scheme_name="BrowserCSRF",
    description="For browser cookie authentication, copy the value of the todo_csrf_token cookie and paste it here.",
    auto_error=False,
)


# Low-level dependency values.
DbSession = Annotated[AsyncSession, Depends(get_session)]
AccessToken = Annotated[str | None, Security(oauth2_scheme)]
PasswordGrantAccessToken = AccessToken
AuthorizationCodeAccessToken = Annotated[str | None, Security(oauth2_authorization_code_scheme)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(bearer_schema)]
AccessCookie = Annotated[str | None, Security(access_cookie_scheme)]
BasicCredentials = Annotated[HTTPBasicCredentials | None, Security(basic_scheme)]
HeaderAPIKey = Annotated[str | None, Security(api_key_header_scheme)]
QueryAPIKey = Annotated[str | None, Security(api_key_query_scheme)]
CSRFHeader = Annotated[str | None, Security(csrf_header_scheme)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def _require_active_user(user: User, mechanism: str) -> User:
    if not user.is_active:
        record_auth_attempt(mechanism, "inactive")
        raise InactiveUserError()

    record_auth_attempt(mechanism, "success")
    return user


def _access_token_user_id(token: str, settings: Settings) -> int:
    try:
        user_id = int(decode_access_token(token, settings).sub)
        if user_id <= 0:
            raise ValueError
    except (InvalidAccessTokenError, TypeError, ValueError) as exc:
        record_auth_attempt(ACCESS_TOKEN_AUTH, "invalid")
        raise InvalidAccessTokenError() from exc

    return user_id


async def _authenticate_access_token(
    token: str,
    settings: Settings,
    session: AsyncSession,
) -> User:
    user_id = _access_token_user_id(token, settings)

    try:
        user = await get_user_by_id(session, user_id)
    except SQLAlchemyError as exc:
        record_auth_attempt(ACCESS_TOKEN_AUTH, "error")
        raise TokenAuthenticationUnavailableError() from exc

    if user is None:
        record_auth_attempt(ACCESS_TOKEN_AUTH, "invalid")
        raise InvalidAccessTokenError()

    return _require_active_user(user, ACCESS_TOKEN_AUTH)


def _select_access_token(explicit_token: str | None, cookie_token: str | None) -> str:
    """Prefer an explicit bearer token and otherwise validate cookie transport."""

    if explicit_token:
        return explicit_token

    if cookie_token:
        return cookie_token

    record_auth_attempt(ACCESS_TOKEN_AUTH, "missing")
    raise InvalidAccessTokenError()


async def get_current_user(
    settings: AppSettings,
    token: PasswordGrantAccessToken,
    cookie_token: AccessCookie,
    session: DbSession,
) -> User:
    """Authenticate an access token obtained through the password flow."""

    selected_token = _select_access_token(token, cookie_token)
    return await _authenticate_access_token(selected_token, settings, session)


async def get_current_authorization_code_user(
    settings: AppSettings,
    token: AuthorizationCodeAccessToken,
    cookie_token: AccessCookie,
    session: DbSession,
) -> User:
    """Authenticate an access token obtained through Authorization Code."""

    selected_token = _select_access_token(token, cookie_token)
    return await _authenticate_access_token(selected_token, settings, session)


async def get_current_bearer_user(
    settings: AppSettings,
    credentials: BearerCredentials,
    cookie_token: AccessCookie,
    session: DbSession,
) -> User:
    """Authenticate the current user from a direct HTTP Bearer token."""

    bearer_token = credentials.credentials if credentials is not None else None
    selected_token = _select_access_token(bearer_token, cookie_token)
    return await _authenticate_access_token(selected_token, settings, session)


async def get_current_basic_user(
    credentials: BasicCredentials,
    session: DbSession,
) -> User:
    """Authenticate an email and password supplied through HTTP Basic."""

    if credentials is None:
        record_auth_attempt(BASIC_AUTH, "missing")
        raise InvalidBasicCredentialsError()

    try:
        user = await get_user_by_email(
            session,
            normalize_email(credentials.username),
        )
    except SQLAlchemyError as exc:
        record_auth_attempt(BASIC_AUTH, "error")
        raise BasicAuthenticationUnavailableError() from exc

    password_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    try:
        valid_password = await to_thread.run_sync(
            verify_password,
            credentials.password,
            password_hash,
        )
    except UnknownHashError as exc:
        record_auth_attempt(BASIC_AUTH, "error")
        raise BasicAuthenticationUnavailableError() from exc

    if user is None or not valid_password:
        record_auth_attempt(BASIC_AUTH, "invalid")
        raise InvalidBasicCredentialsError()

    return _require_active_user(user, BASIC_AUTH)


async def _authenticate_api_key(
    api_key: str | None,
    session: AsyncSession,
    mechanism: str,
) -> User:
    normalized_key = api_key.strip() if api_key else ""
    if not normalized_key:
        record_auth_attempt(mechanism, "missing")
        raise APIKeyRequiredError()

    try:
        record = await get_active_api_key_by_hash(
            session,
            hash_secret(normalized_key),
        )
    except SQLAlchemyError as exc:
        record_auth_attempt(mechanism, "error")
        raise APIKeyServiceError() from exc

    if record is None:
        record_auth_attempt(mechanism, "invalid")
        raise InvalidAPIKeyError()

    return _require_active_user(record.user, mechanism)


async def get_current_header_api_key_user(
    api_key: HeaderAPIKey,
    session: DbSession,
) -> User:
    """Authenticate an API key from the X-API-Key header."""

    return await _authenticate_api_key(api_key, session, HEADER_API_KEY_AUTH)


async def get_current_query_api_key_user(
    api_key: QueryAPIKey,
    session: DbSession,
) -> User:
    """Authenticate an API key from a legacy query parameter."""

    return await _authenticate_api_key(api_key, session, QUERY_API_KEY_AUTH)


def get_api_key_service(session: DbSession) -> APIKeyService:
    return APIKeyService(session=session)


def get_auth_service(session: DbSession, settings: AppSettings) -> AuthService:
    return AuthService(session=session, settings=settings)


def get_email_service(settings: AppSettings) -> EmailService:
    return EmailService(settings=settings)


def get_oauth_service(
    session: DbSession, settings: AppSettings, auth: AuthServiceDep
) -> OAuthService:
    return OAuthService(session=session, settings=settings, auth=auth)


def get_todo_service(session: DbSession) -> TodoService:
    return TodoService(session=session)


def get_user_service(session: DbSession) -> UserService:
    return UserService(session=session)


def _extract_origin(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlsplit(value.strip())

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def validate_request_origin(request: Request) -> None:
    """Reject unsafe browser requests from untrusted origins."""

    if request.method.upper() in SAFE_METHODS:
        return

    settings: Settings = request.app.state.settings
    origin = _extract_origin(request.headers.get("origin"))

    if origin is None:
        uses_browser_session = any(
            name in request.cookies for name in _BROWSER_SESSION_COOKIE_NAMES
        )

        if not uses_browser_session:
            # Allow Bearer, Basic, and API-key clients without Origin.
            return

        origin = _extract_origin(request.headers.get("referer"))

    # Trust requests originating from this API itself.
    request_origin = f"{request.url.scheme}://{request.url.netloc}"

    allowed_origins = {
        *settings.cors_allowed_origins,
        request_origin,
    }

    if origin not in allowed_origins:
        raise RequestOriginNotAllowedError


def _has_explicit_bearer_token(request: Request) -> bool:
    """Check whether the request explicitly uses Bearer authentication."""

    authorization = request.headers.get("Authorization", "")
    scheme, _, credential = authorization.partition(" ")

    return scheme.casefold() == "bearer" and bool(credential.strip())


def require_csrf_token(request: Request, csrf_header: CSRFHeader) -> None:
    """Require CSRF protection when access-cookie authentication is used."""

    if _has_explicit_bearer_token(request):
        return

    if request.cookies.get(ACCESS_COOKIE_NAME) is None:
        return

    if not verify_csrf_token(csrf_header, request.cookies.get(CSRF_COOKIE_NAME)):
        raise InvalidCSRFTokenError()


def require_browser_csrf_token(request: Request, csrf_header: CSRFHeader) -> None:
    """Require CSRF protection for an existing browser cookie session."""

    access_cookie = request.cookies.get(ACCESS_COOKIE_NAME)
    refresh_cookie = request.cookies.get(REFRESH_COOKIE_NAME)

    # Let the endpoint return its own missing-session response.
    if access_cookie is None and refresh_cookie is None:
        return

    if not verify_csrf_token(csrf_header, request.cookies.get(CSRF_COOKIE_NAME)):
        raise InvalidCSRFTokenError()


# Route-facing dependencies.
CurrentUser: TypeAlias = Annotated[User, Depends(get_current_user)]
CurrentAuthorizationCodeUser: TypeAlias = Annotated[
    User, Depends(get_current_authorization_code_user)
]
CurrentBearerUser: TypeAlias = Annotated[User, Depends(get_current_bearer_user)]
CurrentBasicUser: TypeAlias = Annotated[User, Depends(get_current_basic_user)]
CurrentHeaderAPIKeyUser: TypeAlias = Annotated[User, Depends(get_current_header_api_key_user)]
CurrentQueryAPIKeyUser: TypeAlias = Annotated[User, Depends(get_current_query_api_key_user)]
APIKeyServiceDep = Annotated[APIKeyService, Depends(get_api_key_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]
OAuthServiceDep = Annotated[OAuthService, Depends(get_oauth_service)]
TodoServiceDep = Annotated[TodoService, Depends(get_todo_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
