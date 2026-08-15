from __future__ import annotations

from html import escape
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from todo_api.api.deps import OAuthServiceDep
from todo_api.exceptions.auth import (
    EmailNotVerifiedError,
    InactiveUserError,
    InvalidCredentialsError,
)
from todo_api.exceptions.oauth import (
    AuthorizationCodeIssuanceUnavailableError,
    InvalidAuthorizationGrantError,
    InvalidAuthorizationRequestError,
    InvalidCodeChallengeError,
    InvalidOAuthClientError,
    OAuthProtocolError,
    UnsupportedCodeChallengeMethodError,
    UnsupportedGrantTypeError,
    UnsupportedResponseTypeError,
)
from todo_api.schemas.oauth import (
    OAuthAuthorizationRequestSchema,
    OAuthTokenRequestSchema,
)
from todo_api.schemas.token import TokenResponseSchema

router = APIRouter(prefix="/auth", tags=["OAuth2"])

QueryValue = Annotated[str | None, Query()]
FormValue = Annotated[str | None, Form()]
CredentialFormValue = Annotated[str, Form()]

_AUTHORIZE_PATH = "/api/v1/auth/authorize"


def _no_store_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    }


def _html_headers() -> dict[str, str]:
    return {
        **_no_store_headers(),
        "Content-Security-Policy": (
            "default-src 'none'; "
            "style-src 'unsafe-inline'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


def _append_query(uri: str, **values: str | None) -> str:
    parts = urlsplit(uri)
    query = parse_qsl(parts.query, keep_blank_values=True)

    query.extend((key, value) for key, value in values.items() if value is not None)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _validation_fields(exception: ValidationError) -> set[str]:
    return {str(error["loc"][-1]) for error in exception.errors() if error["loc"]}


def _authorization_request(
    *,
    response_type: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    state: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    scope: str | None,
) -> OAuthAuthorizationRequestSchema:
    if response_type is not None and response_type != "code":
        raise UnsupportedResponseTypeError()

    if code_challenge_method is not None and code_challenge_method != "S256":
        raise UnsupportedCodeChallengeMethodError()

    try:
        return OAuthAuthorizationRequestSchema.model_validate(
            {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "scope": scope or "",
            }
        )
    except ValidationError as exc:
        fields = _validation_fields(exc)

        if "code_challenge_method" in fields:
            raise UnsupportedCodeChallengeMethodError() from exc

        if "code_challenge" in fields:
            raise InvalidCodeChallengeError() from exc

        if "client_id" in fields:
            raise InvalidOAuthClientError() from exc

        raise InvalidAuthorizationRequestError() from exc


def _token_request(
    *,
    grant_type: str | None,
    code: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
) -> OAuthTokenRequestSchema:
    if grant_type is not None and grant_type != "authorization_code":
        raise UnsupportedGrantTypeError()

    try:
        return OAuthTokenRequestSchema.model_validate(
            {
                "grant_type": grant_type,
                "code": code,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )
    except ValidationError as exc:
        fields = _validation_fields(exc)

        if "client_id" in fields:
            raise InvalidOAuthClientError() from exc

        if "code_verifier" in fields:
            raise InvalidAuthorizationGrantError() from exc

        raise InvalidAuthorizationRequestError() from exc


def _login_page(request: OAuthAuthorizationRequestSchema, *, error: str = "") -> HTMLResponse:
    hidden_fields = (
        ("response_type", request.response_type),
        ("client_id", request.client_id),
        ("redirect_uri", request.redirect_uri),
        ("state", request.state),
        ("code_challenge", request.code_challenge),
        ("code_challenge_method", request.code_challenge_method),
        ("scope", request.scope),
    )

    hidden_html = "".join(
        f'<input type="hidden" name="{name}" value="{escape(value)}">'
        for name, value in hidden_fields
        if value is not None
    )
    error_html = f'<p class="error">{escape(error)}</p>' if error else ""

    html = f"""<!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Authorize Todo API</title>
            <style>
                body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 8vh auto; padding: 24px; }}
                form, label {{ display: grid; gap: 14px; }}
                label {{ gap: 6px; }}
                input, button {{ box-sizing: border-box; width: 100%; padding: 11px; font: inherit; }}
                button {{ cursor: pointer; }}
                .error {{ color: #b00020; }}
            </style>
        </head>
        <body>
            <h1>Todo API</h1>
            <p>Sign in to authorize <strong>{escape(request.client_id)}</strong>.</p>
            {error_html}
            <form method="post" action="{_AUTHORIZE_PATH}" autocomplete="on">
                {hidden_html}
                <label>
                    Email
                    <input name="email" type="email" autocomplete="username" required>
                </label>
                <label>
                    Password
                    <input name="password" type="password" autocomplete="current-password" required>
                </label>
                <button type="submit">Authorize</button>
            </form>
        </body>
        </html>
    """

    return HTMLResponse(content=html, headers=_html_headers())


def _has_trusted_redirect(
    oauth: OAuthServiceDep,
    *,
    client_id: str | None,
    redirect_uri: str | None,
) -> bool:
    return (
        client_id == oauth.settings.oauth2_public_client_id
        and redirect_uri is not None
        and redirect_uri in oauth.settings.oauth2_redirect_uris
    )


def _redirect_authorization_error(
    oauth: OAuthServiceDep,
    exception: OAuthProtocolError | AuthorizationCodeIssuanceUnavailableError,
    *,
    client_id: str | None,
    redirect_uri: str | None,
    state: str | None,
) -> RedirectResponse:
    """Redirect an OAuth error only to an already trusted redirect URI."""

    if not _has_trusted_redirect(
        oauth,
        client_id=client_id,
        redirect_uri=redirect_uri,
    ):
        raise exception

    assert redirect_uri is not None

    location = _append_query(
        redirect_uri,
        error=exception.oauth_error,
        error_description=exception.public_message,
        state=state,
    )

    return RedirectResponse(
        url=location,
        status_code=status.HTTP_302_FOUND,
        headers=_no_store_headers(),
    )


@router.get(
    "/authorize",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def authorization_page(
    service: OAuthServiceDep,
    response_type: QueryValue = None,
    client_id: QueryValue = None,
    redirect_uri: QueryValue = None,
    state: QueryValue = None,
    code_challenge: QueryValue = None,
    code_challenge_method: QueryValue = None,
    scope: QueryValue = "",
) -> HTMLResponse | RedirectResponse:
    try:
        request = _authorization_request(
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
        )

        service.validate_authorization_request(request)
    except OAuthProtocolError as exc:
        return _redirect_authorization_error(
            oauth,
            exc,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
        )

    return _login_page(request)


@router.post(
    "/authorize",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def authorize(
    service: OAuthServiceDep,
    email: CredentialFormValue,
    password: CredentialFormValue,
    response_type: FormValue = None,
    client_id: FormValue = None,
    redirect_uri: FormValue = None,
    state: FormValue = None,
    code_challenge: FormValue = None,
    code_challenge_method: FormValue = None,
    scope: FormValue = "",
) -> HTMLResponse | RedirectResponse:
    try:
        request = _authorization_request(
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
        )
    except OAuthProtocolError as exc:
        return _redirect_authorization_error(
            service,
            exc,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
        )

    try:
        code = await service.issue_authorization_code(
            email=email,
            password=password,
            request=request,
        )
    except (InvalidCredentialsError, InactiveUserError, EmailNotVerifiedError):
        return _login_page(request, error="Invalid email or password.")
    except (OAuthProtocolError, AuthorizationCodeIssuanceUnavailableError) as exc:
        return _redirect_authorization_error(
            service,
            exc,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
        )

    location = _append_query(
        request.redirect_uri,
        code=code,
        state=request.state,
    )

    return RedirectResponse(
        url=location,
        status_code=status.HTTP_303_SEE_OTHER,
        headers=_no_store_headers(),
    )


@router.post(
    "/token",
    response_model=TokenResponseSchema,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "OAuth 2.0 token request error.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "OAuth client authentication failed.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "OAuth token exchange is unavailable.",
        },
    },
)
async def exchange_code(
    oauth: OAuthServiceDep,
    http_request: Request,
    response: Response,
    grant_type: FormValue = None,
    code: FormValue = None,
    client_id: FormValue = None,
    redirect_uri: FormValue = None,
    code_verifier: FormValue = None,
) -> TokenResponseSchema:
    if http_request.headers.get("Authorization"):
        raise InvalidOAuthClientError()

    request = _token_request(
        grant_type=grant_type,
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )

    tokens = await oauth.exchange_authorization_code(request=request)

    response.headers.update(_no_store_headers())

    return tokens
