from __future__ import annotations

from typing import Annotated

from anyio import to_thread
from fastapi import Depends, Request, Security
from fastapi.security import (
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from pwdlib.exceptions import UnknownHashError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import Settings
from todo_api.core.security import (
    API_KEY_HEADER,
    DUMMY_PASSWORD_HASH,
    decode_access_token,
    hash_secret,
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
    TokenAuthenticationUnavailableError,
)
from todo_api.models.user import User
from todo_api.observability.metrics import record_auth_attempt
from todo_api.repositories.api_key import get_active_api_key_by_hash
from todo_api.repositories.user import get_user_by_email, get_user_by_id
from todo_api.services.todo import TodoService
from todo_api.utils.email import normalize_email

ACCESS_TOKEN_AUTH = "access_token"
BASIC_AUTH = "basic"
HEADER_API_KEY_AUTH = "api_key_header"
QUERY_API_KEY_AUTH = "api_key_query"


# Security transports. OAuth2PasswordBearer is the single access-token transport.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scheme_name="OAuth2PasswordBearer",
)
bearer_schema = HTTPBearer(
    scheme_name="HTTPBearer",
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


# Low-level dependency values.
DbSession = Annotated[AsyncSession, Depends(get_session)]
AccessToken = Annotated[str, Security(oauth2_scheme)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials, Security(bearer_schema)]
BasicCredentials = Annotated[HTTPBasicCredentials | None, Security(basic_scheme)]
HeaderAPIKey = Annotated[str | None, Security(api_key_header_scheme)]
QueryAPIKey = Annotated[str | None, Security(api_key_query_scheme)]


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


async def get_current_user(
    settings: AppSettings,
    token: AccessToken,
    session: DbSession,
) -> User:
    """Authenticate the current user from an OAuth2 bearer access token."""

    return await _authenticate_access_token(token, settings, session)


async def get_current_bearer_user(
    settings: AppSettings,
    credentials: BearerCredentials,
    session: DbSession,
) -> User:
    """Authenticate the current user from a direct HTTP Bearer token."""

    return await _authenticate_access_token(credentials.credentials, settings, session)


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


def get_todo_service(session: DbSession) -> TodoService:
    return TodoService(session=session)


# Route-facing dependencies.
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentBearerUser = Annotated[User, Depends(get_current_bearer_user)]
CurrentBasicUser = Annotated[User, Depends(get_current_basic_user)]
CurrentHeaderAPIKeyUser = Annotated[User, Depends(get_current_header_api_key_user)]
CurrentQueryAPIKeyUser = Annotated[User, Depends(get_current_query_api_key_user)]
TodoServiceDep = Annotated[TodoService, Depends(get_todo_service)]
