from __future__ import annotations

from fastapi_mail import ConnectionConfig

from todo_api.core.config import Settings


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def create_mail_config(settings: Settings) -> ConnectionConfig:
    """Translate application settings into FastAPI-Mail's SMTP configuration."""

    return ConnectionConfig(
        MAIL_USERNAME=settings.mail_username,
        MAIL_PASSWORD=settings.mail_password,
        MAIL_PORT=settings.mail_port,
        MAIL_SERVER=settings.mail_server,
        MAIL_STARTTLS=settings.mail_starttls,
        MAIL_SSL_TLS=settings.mail_ssl_tls,
        MAIL_DEBUG=settings.mail_debug,
        MAIL_FROM=settings.mail_from,
        MAIL_FROM_NAME=settings.mail_from_name,
        TEMPLATE_FOLDER=settings.mail_template_folder,
        SUPPRESS_SEND=int(settings.mail_suppress_send),
        USE_CREDENTIALS=settings.mail_use_credentials,
        VALIDATE_CERTS=settings.mail_validate_certs,
        TIMEOUT=settings.mail_timeout_seconds,
        LOCAL_HOSTNAME=settings.mail_local_hostname,
        CERT_BUNDLE=str(settings.mail_cert_bundle) if settings.mail_cert_bundle else None,
    )
