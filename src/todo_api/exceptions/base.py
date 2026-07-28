from __future__ import annotations


class ApplicationError(Exception):
    error_code = "application_error"
    public_message = "An application error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.public_message = message or type(self).public_message
        super().__init__(self.public_message)
