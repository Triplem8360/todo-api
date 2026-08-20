from __future__ import annotations

import asyncio
from email.utils import getaddresses

from fastapi_mail import MessageType

from todo_api.core.config import Settings
from todo_api.services.email import EmailService
from todo_api.utils.email import create_mail_config, create_verification_email, create_welcome_email

TEST_SECRET = "test-secret-key-with-at-least-thirty-two-bytes"


def mail_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key=TEST_SECRET,
        mail_suppress_send=True,
        **overrides,
    )


def test_create_mail_config_maps_all_connection_fields() -> None:
    settings = mail_settings(
        mail_server="smtp.example.com",
        mail_port=587,
        mail_username="smtp-user",
        mail_password="smtp-password",
        mail_use_credentials=True,
        mail_starttls=True,
        mail_from="sender@example.com",
        mail_from_name="Todo Mailer",
        mail_timeout_seconds=12,
        mail_local_hostname="api.example.com",
    )

    config = create_mail_config(settings)

    assert config.MAIL_SERVER == "smtp.example.com"
    assert config.MAIL_PORT == 587
    assert config.MAIL_USERNAME == "smtp-user"
    assert config.MAIL_PASSWORD.get_secret_value() == "smtp-password"
    assert config.USE_CREDENTIALS is True
    assert config.MAIL_STARTTLS is True
    assert config.MAIL_SSL_TLS is False
    assert str(config.MAIL_FROM) == "sender@example.com"
    assert config.MAIL_FROM_NAME == "Todo Mailer"
    assert config.SUPPRESS_SEND == 1
    assert config.TIMEOUT == 12
    assert config.LOCAL_HOSTNAME == "api.example.com"


def test_suppressed_send_builds_the_expected_message_without_network() -> None:
    service = EmailService(mail_settings())

    with service.mailer.record_messages() as outbox:
        delivered = asyncio.run(
            service.send(
                recipient="recipient@example.com",
                subject="SMTP test",
                body="Delivery works.",
                subtype=MessageType.plain,
            )
        )

    assert delivered is False
    assert len(outbox) == 1
    assert getaddresses([outbox[0]["To"]]) == [("recipient", "recipient@example.com")]
    assert outbox[0]["Subject"] == "SMTP test"
    body_part = next(part for part in outbox[0].walk() if part.get_content_type() == "text/plain")
    body = body_part.get_payload(decode=True).decode(body_part.get_content_charset() or "utf-8")
    assert "Delivery works." in body


def test_suppressed_connection_check_does_not_use_network() -> None:
    service = EmailService(mail_settings())

    assert asyncio.run(service.check_connection()) is False


def test_verification_email_contains_a_safe_single_use_link() -> None:
    message = create_verification_email(
        mail_settings(),
        token="opaque_token-value",
        full_name="<Test User>",
    )

    assert (
        "http://localhost:8000/api/v1/auth/email-verification/confirm" "?token=opaque_token-value"
    ) in message.plain_body
    assert "&lt;Test User&gt;" in message.html_body
    assert "<Test User>" not in message.html_body
    assert "multipart" not in message.subject.casefold()


def test_welcome_email_escapes_the_recipient_name() -> None:
    message = create_welcome_email(mail_settings(), full_name="<Test User>")

    assert message.subject == "Welcome to Todo API"
    assert "&lt;Test User&gt;" in message.html_body
    assert "<Test User>" not in message.html_body
    assert "Your Todo API account is ready" in message.plain_body
