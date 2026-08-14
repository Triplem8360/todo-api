from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi_mail import MessageType

from todo_api.api.deps import (
    CurrentBearerUser,
    EmailServiceDep,
    require_csrf_token,
    validate_request_origin,
)
from todo_api.api.responses import error_response
from todo_api.exceptions.auth import (
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCSRFTokenError,
    RequestOriginNotAllowedError,
)
from todo_api.exceptions.email import EmailServiceUnavailableError
from todo_api.schemas.email import (
    EmailDeliveryResponseSchema,
    EmailTestRequestSchema,
    SMTPConnectionResponseSchema,
)

router = APIRouter(prefix="/emails", tags=["Emails"])

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: error_response(
        InvalidAccessTokenError,
        description="Access token is invalid or expired.",
        authenticate="Bearer",
    ),
    status.HTTP_403_FORBIDDEN: error_response(
        InactiveUserError,
        description="The authenticated user is not allowed to access this resource.",
    ),
}

_EMAIL_UNAVAILABLE_RESPONSE = error_response(
    EmailServiceUnavailableError,
    description="The configured SMTP service could not be reached.",
)


@router.get(
    "/smtp",
    response_model=SMTPConnectionResponseSchema,
    summary="Check the SMTP connection",
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_503_SERVICE_UNAVAILABLE: _EMAIL_UNAVAILABLE_RESPONSE,
    },
)
async def check_smtp_connection(
    service: EmailServiceDep, _current_user: CurrentBearerUser
) -> SMTPConnectionResponseSchema:
    connected = await service.check_connection()

    return SMTPConnectionResponseSchema(
        status="ok" if connected else "suppressed",
        server=service.config.MAIL_SERVER,
        port=service.config.MAIL_PORT,
        starttls=service.config.MAIL_STARTTLS,
        ssl_tls=service.config.MAIL_SSL_TLS,
        use_credentials=service.config.USE_CREDENTIALS,
        validate_certs=service.config.VALIDATE_CERTS,
    )


@router.post(
    "/test",
    response_model=EmailDeliveryResponseSchema,
    summary="Send a test email to the authenticated user",
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_403_FORBIDDEN: error_response(
            InactiveUserError,
            InvalidCSRFTokenError,
            RequestOriginNotAllowedError,
            description="The authenticated browser request was rejected.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: _EMAIL_UNAVAILABLE_RESPONSE,
    },
    dependencies=[Depends(validate_request_origin), Depends(require_csrf_token)],
)
async def send_test_email(
    payload: EmailTestRequestSchema,
    service: EmailServiceDep,
    current_user: CurrentBearerUser,
) -> EmailDeliveryResponseSchema:
    delivered = await service.send(
        recipient=current_user.email,
        subject=payload.subject,
        body=payload.body,
        subtype=MessageType(payload.subtype),
    )

    return EmailDeliveryResponseSchema(
        status="sent" if delivered else "suppressed",
        recipient=current_user.email,
    )
