from __future__ import annotations

import pytest
from pydantic import ValidationError

from todo_api.schemas.oauth import (
    OAuthAuthorizationRequestSchema,
    OAuthTokenRequestSchema,
)

VALID_CHALLENGE = "A" * 43


def test_authorization_state_is_optional() -> None:
    request = OAuthAuthorizationRequestSchema(
        response_type="code",
        client_id="public-client",
        redirect_uri="https://client.example/callback",
        code_challenge=VALID_CHALLENGE,
        code_challenge_method="S256",
    )

    assert request.state is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code_challenge", "short"),
        ("code_challenge", "." * 43),
        ("code_challenge_method", "plain"),
    ],
)
def test_authorization_request_rejects_non_s256_pkce(field: str, value: str) -> None:
    values = {
        "response_type": "code",
        "client_id": "public-client",
        "redirect_uri": "https://client.example/callback",
        "code_challenge": VALID_CHALLENGE,
        "code_challenge_method": "S256",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        OAuthAuthorizationRequestSchema.model_validate(values)


@pytest.mark.parametrize("verifier", ["A" * 42, "A" * 129, "!" * 43])
def test_token_request_rejects_invalid_pkce_verifier(verifier: str) -> None:
    with pytest.raises(ValidationError):
        OAuthTokenRequestSchema(
            grant_type="authorization_code",
            client_id="public-client",
            redirect_uri="https://client.example/callback",
            code="authorization-code",
            code_verifier=verifier,
        )


def test_redirect_uri_is_not_normalized() -> None:
    redirect_uri = "https://client.example/callback?next=%2Ftodos"
    request = OAuthAuthorizationRequestSchema(
        response_type="code",
        client_id="public-client",
        redirect_uri=redirect_uri,
        code_challenge=VALID_CHALLENGE,
        code_challenge_method="S256",
    )

    assert request.redirect_uri == redirect_uri


def test_redirect_uri_rejects_an_empty_fragment_component() -> None:
    with pytest.raises(ValidationError):
        OAuthAuthorizationRequestSchema(
            response_type="code",
            client_id="public-client",
            redirect_uri="https://client.example/callback#",
            code_challenge=VALID_CHALLENGE,
            code_challenge_method="S256",
        )
