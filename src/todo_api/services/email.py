from __future__ import annotations

from aiosmtplib.errors import SMTPException
from fastapi_mail import FastMail, MessageSchema, MessageType
from fastapi_mail.connection import Connection
from fastapi_mail.errors import ConnectionErrors

from todo_api.core.config import Settings
from todo_api.exceptions.email import EmailServiceUnavailableError
from todo_api.utils.email import create_mail_config


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.config = create_mail_config(settings)
        self.mailer = FastMail(self.config)

    @property
    def suppresses_delivery(self) -> bool:
        return bool(self.config.SUPPRESS_SEND)

    async def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        subtype: MessageType = MessageType.plain,
    ) -> bool:
        message = MessageSchema(
            subject=subject,
            recipients=[recipient],
            body=body,
            subtype=subtype,
        )

        try:
            await self.mailer.send_message(message)
        except (ConnectionErrors, SMTPException, OSError, TimeoutError) as exc:
            raise EmailServiceUnavailableError() from exc

        return not self.suppresses_delivery

    async def check_connection(self) -> bool:
        if self.suppresses_delivery:
            return False

        try:
            # FastAPI-Mail's connection context performs the SMTP handshake,
            # optional TLS negotiation/login, and a clean QUIT on exit.
            async with Connection(self.config):
                pass
        except (ConnectionErrors, SMTPException, OSError, TimeoutError) as exc:
            raise EmailServiceUnavailableError() from exc

        return True
