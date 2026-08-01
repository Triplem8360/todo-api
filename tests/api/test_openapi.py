from __future__ import annotations

from todo_api.app import create_app
from todo_api.core.config import Settings


def test_openapi_exposes_compact_authentication_surface(settings: Settings) -> None:
    schema = create_app(settings).openapi()

    assert set(schema["paths"]) >= {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/token",
        "/api/v1/api-keys",
        "/api/v1/users/me",
        "/api/v1/users/me/api-key",
        "/api/v1/users/me/basic",
        "/api/v1/users/me/query-api-key",
    }
    assert set(schema["paths"]["/api/v1/users/me"]) >= {"get", "patch", "delete"}
    assert schema["paths"]["/api/v1/users/me/query-api-key"]["get"]["deprecated"] is True
    assert set(schema["components"]["securitySchemes"]) == {
        "APIKeyHeaderAuth",
        "APIKeyQueryAuth",
        "BasicAuth",
        "HTTPBearer",
        "OAuth2AuthorizationCodeBearer",
        "OAuth2PasswordBearer",
    }

    oauth_flow = schema["components"]["securitySchemes"]["OAuth2AuthorizationCodeBearer"]["flows"][
        "authorizationCode"
    ]
    assert oauth_flow["authorizationUrl"] == "/api/v1/auth/authorize"
    assert oauth_flow["tokenUrl"] == "/api/v1/auth/token"
