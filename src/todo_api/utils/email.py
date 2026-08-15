from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import urlencode

from fastapi_mail import ConnectionConfig

from todo_api.core.config import Settings


def normalize_email(email: str) -> str:
    return email.strip().casefold()


@dataclass(frozen=True, slots=True)
class VerificationEmail:
    subject: str
    html_body: str
    plain_body: str


def create_verification_email(
    settings: Settings,
    *,
    token: str,
    full_name: str | None,
) -> VerificationEmail:
    verification_url = f"{settings.email_verification_url}?{urlencode({'token': token})}"
    greeting_name = full_name or "there"
    safe_name = escape(greeting_name)
    safe_url = escape(verification_url, quote=True)
    ttl_hours = settings.email_verification_token_ttl.total_seconds() / 3600
    ttl_label = f"{ttl_hours:g} hours"

    subject = f"Verify your {settings.app_name} email"
    plain_body = (
        f"Hello {greeting_name},\n\n"
        f"Verify your email address for {settings.app_name} by opening this link:\n"
        f"{verification_url}\n\n"
        f"This single-use link expires in {ttl_label}. "
        "If you did not create this account, you can ignore this email."
    )
    html_body = f"""
    <div style="font-family: sans-serif; line-height: 1.5; color: #1f2937">
      <h2>Verify your email</h2>
      <p>Hello {safe_name},</p>
      <p>Confirm your email address to finish setting up your {escape(settings.app_name)} account.</p>
      <p>
        <a href="{safe_url}"
           style="display: inline-block; padding: 10px 16px; color: white; background: #2563eb; text-decoration: none; border-radius: 6px">
          Verify email
        </a>
      </p>
      <p>This single-use link expires in {ttl_label}.</p>
      <p>If you did not create this account, you can ignore this email.</p>
    </div>
    """.strip()

    return VerificationEmail(
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
    )


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
