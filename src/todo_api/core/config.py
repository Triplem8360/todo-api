from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import DirectoryPath, EmailStr, Field, SecretStr, field_validator, model_validator
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
    cache_backend: Literal["memory", "redis"] = Field(
        default="redis", validation_alias="CACHE_BACKEND"
    )
    cache_prefix: str = Field(default="todo-api", validation_alias="CACHE_PREFIX")
    cache_ttl_seconds: int = Field(
        default=60,
        ge=1,
        le=3_600,
        validation_alias="CACHE_TTL_SECONDS",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
        repr=False,
    )
    redis_connect_timeout_seconds: float = Field(
        default=2,
        gt=0,
        le=60,
        validation_alias="REDIS_CONNECT_TIMEOUT_SECONDS",
    )
    redis_socket_timeout_seconds: float = Field(
        default=2,
        gt=0,
        le=60,
        validation_alias="REDIS_SOCKET_TIMEOUT_SECONDS",
    )
    apscheduler_redis_db: int = Field(
        default=1,
        ge=0,
        validation_alias="APSCHEDULER_REDIS_DB",
    )
    apscheduler_jobs_key: str = Field(
        default="todo-api:apscheduler:jobs",
        min_length=1,
        validation_alias="APSCHEDULER_JOBS_KEY",
    )
    apscheduler_run_times_key: str = Field(
        default="todo-api:apscheduler:run-times",
        min_length=1,
        validation_alias="APSCHEDULER_RUN_TIMES_KEY",
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/2",
        validation_alias="CELERY_BROKER_URL",
        repr=False,
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/3",
        validation_alias="CELERY_RESULT_BACKEND",
        repr=False,
    )
    celery_result_expires_seconds: int = Field(
        default=3_600,
        ge=60,
        le=604_800,
        validation_alias="CELERY_RESULT_EXPIRES_SECONDS",
    )
    celery_task_always_eager: bool = Field(
        default=False,
        validation_alias="CELERY_TASK_ALWAYS_EAGER",
    )
    completed_todo_auto_archive_days: int = Field(
        default=30,
        ge=0,
        le=3_650,
        validation_alias="COMPLETED_TODO_AUTO_ARCHIVE_DAYS",
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

    mail_username: str = Field(default="", validation_alias="MAIL_USERNAME")
    mail_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="MAIL_PASSWORD",
        repr=False,
    )
    mail_port: int = Field(default=2525, ge=1, le=65_535, validation_alias="MAIL_PORT")
    mail_server: str = Field(default="localhost", min_length=1, validation_alias="MAIL_SERVER")
    mail_starttls: bool = Field(default=False, validation_alias="MAIL_STARTTLS")
    mail_ssl_tls: bool = Field(default=False, validation_alias="MAIL_SSL_TLS")
    mail_debug: int = Field(default=0, ge=0, le=1, validation_alias="MAIL_DEBUG")
    mail_from: EmailStr = Field(default="noreply@example.com", validation_alias="MAIL_FROM")
    mail_from_name: str | None = Field(default="Todo API", validation_alias="MAIL_FROM_NAME")
    mail_template_folder: DirectoryPath | None = Field(
        default=None, validation_alias="TEMPLATE_FOLDER"
    )
    mail_suppress_send: bool = Field(default=False, validation_alias="SUPPRESS_SEND")
    mail_use_credentials: bool = Field(default=False, validation_alias="USE_CREDENTIALS")
    mail_validate_certs: bool = Field(default=True, validation_alias="VALIDATE_CERTS")
    mail_timeout_seconds: int = Field(default=10, gt=0, le=300, validation_alias="TIMEOUT")
    mail_local_hostname: str | None = Field(default=None, validation_alias="LOCAL_HOSTNAME")
    mail_cert_bundle: Path | None = Field(default=None, validation_alias="CERT_BUNDLE")
    email_verification_url: str = Field(
        default="http://localhost:8000/api/v1/auth/email-verification/confirm",
        validation_alias="EMAIL_VERIFICATION_URL",
    )
    email_verification_token_ttl: timedelta = Field(
        default=timedelta(hours=24),
        gt=timedelta(0),
        validation_alias="EMAIL_VERIFICATION_TOKEN_TTL",
    )
    email_verification_resend_cooldown: timedelta = Field(
        default=timedelta(seconds=60),
        ge=timedelta(0),
        validation_alias="EMAIL_VERIFICATION_RESEND_COOLDOWN",
    )

    @field_validator(
        "mail_from_name",
        "mail_template_folder",
        "mail_local_hostname",
        "mail_cert_bundle",
        mode="before",
    )
    @classmethod
    def empty_mail_options_are_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("mail_server")
    @classmethod
    def validate_mail_server(cls, value: str) -> str:
        server = value.strip()
        if not server:
            raise ValueError("MAIL_SERVER must not be blank.")
        return server

    @field_validator("email_verification_url")
    @classmethod
    def validate_email_verification_url(cls, value: str) -> str:
        url = value.strip()
        parsed = urlsplit(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("EMAIL_VERIFICATION_URL must be an absolute HTTP(S) URL.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("EMAIL_VERIFICATION_URL must not include user information.")
        if parsed.query or parsed.fragment:
            raise ValueError("EMAIL_VERIFICATION_URL must not include a query or fragment.")

        return url

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

    @field_validator("redis_url")
    @classmethod
    def require_redis_url(cls, value: str) -> str:
        parsed = urlsplit(value)

        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError("REDIS_URL must use the redis:// or rediss:// scheme.")

        if not parsed.hostname:
            raise ValueError("REDIS_URL must include a host.")

        if parsed.fragment:
            raise ValueError("REDIS_URL must not include a fragment.")

        return value

    @field_validator("celery_broker_url", "celery_result_backend")
    @classmethod
    def require_celery_redis_url(cls, value: str) -> str:
        parsed = urlsplit(value)

        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError("Celery Redis URLs must use the redis:// or rediss:// scheme.")

        if not parsed.hostname:
            raise ValueError("Celery Redis URLs must include a host.")

        if parsed.fragment:
            raise ValueError("Celery Redis URLs must not include a fragment.")

        return value

    @field_validator("apscheduler_jobs_key", "apscheduler_run_times_key")
    @classmethod
    def validate_apscheduler_redis_key(cls, value: str) -> str:
        key = value.strip()
        if not key:
            raise ValueError("APScheduler Redis keys must not be empty.")
        return key

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
        if self.apscheduler_jobs_key == self.apscheduler_run_times_key:
            raise ValueError("APSCHEDULER_JOBS_KEY and APSCHEDULER_RUN_TIMES_KEY must differ.")

        if self.mail_starttls and self.mail_ssl_tls:
            raise ValueError("MAIL_STARTTLS and MAIL_SSL_TLS cannot both be enabled.")

        if self.mail_use_credentials and (
            not self.mail_username.strip() or not self.mail_password.get_secret_value()
        ):
            raise ValueError(
                "MAIL_USERNAME and MAIL_PASSWORD are required when USE_CREDENTIALS is enabled."
            )

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

            if urlsplit(self.email_verification_url).scheme != "https":
                raise ValueError("EMAIL_VERIFICATION_URL must use HTTPS in staging and production.")

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
