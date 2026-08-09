from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

HMAC_MINIMUM_KEY_BYTES = {"HS256": 32, "HS384": 48, "HS512": 64}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    app_name: str = Field(default="Todo API", validation_alias="APP_NAME")
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    app_debug: bool = Field(default=False, validation_alias="APP_DEBUG")

    allowed_hosts: tuple[str, ...] = Field(
        default=("localhost", "127.0.0.1", "testserver"),
        min_length=1,
        validation_alias="ALLOWED_HOSTS",
    )

    cors_allowed_origins: tuple[str, ...] = Field(
        default=("http://localhost:5500",),
        validation_alias="CORS_ALLOWED_ORIGINS",
    )
    cors_max_age_seconds: int = Field(
        default=600,
        ge=0,
        le=86_400,
        validation_alias="CORS_MAX_AGE_SECONDS",
    )

    cache_enabled: bool = Field(default=True, validation_alias="CACHE_ENABLED")
    cache_prefix: str = Field(default="todo-api", validation_alias="CACHE_PREFIX")
    cache_ttl_seconds: int = Field(
        default=60,
        ge=1,
        le=3_600,
        validation_alias="CACHE_TTL_SECONDS",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://todo:todo@localhost:5432/todo",
        validation_alias="DATABASE_URL",
        repr=False,
    )
    sql_echo: bool = Field(default=False, validation_alias="SQL_ECHO")
    db_pool_size: int = Field(default=10, ge=1, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(
        default=10,
        ge=0,
        validation_alias="DB_MAX_OVERFLOW",
    )
    db_pool_timeout_seconds: float = Field(
        default=30,
        gt=0,
        validation_alias="DB_POOL_TIMEOUT_SECONDS",
    )
    db_pool_recycle_seconds: int = Field(
        default=1800,
        ge=-1,
        validation_alias="DB_POOL_RECYCLE_SECONDS",
    )
    db_connect_timeout_seconds: float = Field(
        default=5,
        gt=0,
        validation_alias="DB_CONNECT_TIMEOUT_SECONDS",
    )
    db_command_timeout_seconds: float = Field(
        default=30,
        gt=0,
        validation_alias="DB_COMMAND_TIMEOUT_SECONDS",
    )
    db_healthcheck_timeout_seconds: float = Field(
        default=2,
        gt=0,
        validation_alias="DB_HEALTHCHECK_TIMEOUT_SECONDS",
    )

    secret_key: SecretStr = Field(
        default=SecretStr("change-this-secret-key-in-real-projects"),
        validation_alias="SECRET_KEY",
        repr=False,
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    jwt_issuer: str = Field(default="todo-api", validation_alias="JWT_ISSUER")
    jwt_access_audience: str = Field(
        default="todo-api",
        validation_alias="JWT_ACCESS_AUDIENCE",
    )
    jwt_refresh_audience: str = Field(
        default="todo-api-refresh",
        validation_alias="JWT_REFRESH_AUDIENCE",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        gt=0,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=30,
        gt=0,
        validation_alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    refresh_session_absolute_ttl: timedelta = Field(
        default=timedelta(days=90),
        gt=timedelta(0),
        validation_alias="REFRESH_SESSION_ABSOLUTE_TTL",
    )
    refresh_token_reuse_grace: timedelta = Field(
        default=timedelta(seconds=5),
        ge=timedelta(0),
        validation_alias="REFRESH_TOKEN_REUSE_GRACE",
    )
    auth_cookie_secure: bool = Field(
        default=False,
        validation_alias="AUTH_COOKIE_SECURE",
    )
    auth_cookie_samesite: Literal["lax", "strict"] = Field(
        default="lax",
        validation_alias="AUTH_COOKIE_SAMESITE",
    )

    oauth2_public_client_id: str = Field(
        default="todo-public-client",
        min_length=1,
        max_length=128,
        validation_alias="OAUTH2_PUBLIC_CLIENT_ID",
    )
    oauth2_redirect_uris: tuple[str, ...] = Field(
        default=("http://localhost:8000/docs/oauth2-redirect",),
        min_length=1,
        validation_alias="OAUTH2_REDIRECT_URIS",
    )
    oauth2_authorization_code_ttl_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        validation_alias="OAUTH2_AUTHORIZATION_CODE_TTL_SECONDS",
    )

    metrics_path: str = Field(default="/metrics", validation_alias="METRICS_PATH")

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        validated: list[str] = []
        seen: set[str] = set()

        for raw_host in values:
            host = raw_host.strip().casefold()

            if not host:
                raise ValueError("ALLOWED_HOSTS must not contain empty values.")

            if host == "*":
                raise ValueError(
                    "ALLOWED_HOSTS must not contain '*'. Configure trusted hosts explicitly."
                )

            if "://" in host or "/" in host or "?" in host or "#" in host or ":" in host:
                raise ValueError(
                    "Each allowed host must be a hostname without a scheme, path, query, fragment, or port."
                )

            if "*" in host and not (host.startswith("*.") and host.count("*") == 1):
                raise ValueError("Wildcard hosts must use the '*.example.com' format.")

            if host in seen:
                raise ValueError(f"Duplicate allowed host configured: {host}")

            seen.add(host)
            validated.append(host)

        return tuple(validated)

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        validated: list[str] = []
        seen: set[str] = set()

        for raw_origin in values:
            origin = raw_origin.strip()

            if not origin:
                raise ValueError("CORS origins must not be empty.")

            if origin == "*":
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS cannot contain '*' when credentialed browser requests are enabled."
                )

            parsed = urlsplit(origin)

            if parsed.scheme not in {"http", "https"}:
                raise ValueError("Each CORS origin must use the http or https scheme.")

            if not parsed.netloc:
                raise ValueError("Each CORS origin must include a host.")

            if parsed.username is not None or parsed.password is not None:
                raise ValueError("CORS origins must not include user information.")

            if parsed.path not in {"", "/"}:
                raise ValueError("CORS origins must not include a path.")

            if parsed.query:
                raise ValueError("CORS origins must not include a query string.")

            if parsed.fragment:
                raise ValueError("CORS origins must not include a fragment.")

            normalized = f"{parsed.scheme.casefold()}://{parsed.netloc.casefold()}"
            if normalized in seen:
                raise ValueError(f"Duplicate CORS origin configured: {normalized}")

            seen.add(normalized)
            validated.append(normalized)

        return tuple(validated)

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql_url(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+asyncpg":
            raise ValueError(
                "DATABASE_URL must use PostgreSQL with the asyncpg driver "
                "(postgresql+asyncpg://...)."
            )
        return value

    @field_validator("metrics_path")
    @classmethod
    def validate_metrics_path(cls, value: str) -> str:
        if not value.startswith("/") or value == "/":
            raise ValueError("METRICS_PATH must start with '/' and cannot be '/'.")
        return value.rstrip("/")

    @field_validator("oauth2_redirect_uris")
    @classmethod
    def validate_oauth2_redirect_uris(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        validated = []
        seen = set()

        for raw_uri in values:
            uri = raw_uri.strip()
            parsed = urlsplit(uri)

            if not parsed.scheme:
                raise ValueError("Each OAuth redirect URI must be an absolute URI.")

            if parsed.scheme in {"http", "https"} and not parsed.netloc:
                raise ValueError("HTTP OAuth redirect URIs must include a host.")

            if "#" in uri:
                raise ValueError("OAuth redirect URIs must not contain fragments.")

            if uri in seen:
                raise ValueError(f"Duplicate OAuth redirect URI configured: {uri}")

            seen.add(uri)
            validated.append(uri)

        return tuple(validated)

    @model_validator(mode="after")
    def validate_signing_secret(self) -> Settings:
        secret = self.secret_key.get_secret_value()
        minimum_size = HMAC_MINIMUM_KEY_BYTES[self.jwt_algorithm]
        secret_size = len(secret.encode())
        if secret_size < minimum_size:
            raise ValueError(
                f"SECRET_KEY must contain at least {minimum_size} bytes when "
                f"JWT_ALGORITHM={self.jwt_algorithm}; got {secret_size} bytes."
            )

        if self.app_env in {"staging", "production"}:
            normalized = secret.strip().casefold()
            if len(set(normalized)) < 8 or normalized.startswith("change-this"):
                raise ValueError("SECRET_KEY must be a strong, randomly generated value.")

            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be enabled in staging and production.")

            for origin in self.cors_allowed_origins:
                parsed = urlsplit(origin)

                if parsed.scheme != "https":
                    raise ValueError(
                        "CORS_ALLOWED_ORIGINS must use HTTPS in staging and production."
                    )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
