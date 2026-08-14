from __future__ import annotations

from todo_api.exceptions.base import ApplicationError


class EmailServiceUnavailableError(ApplicationError):
    error_code = "email_service_unavailable"
    public_message = "The email service is temporarily unavailable."
