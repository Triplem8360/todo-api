from __future__ import annotations

from todo_api.exceptions.base import ApplicationError


class TodoServiceError(ApplicationError):
    """Base exception for Todo operations."""

    error_code = "todo_service_error"
    public_message = "Todo operation failed."


class TodoNotFoundError(TodoServiceError):
    error_code = "todo_not_found"
    public_message = "Todo not found."


class TodoStateConflictError(TodoServiceError):
    error_code = "todo_state_conflict"
    public_message = "The requested Todo status transition is not allowed."


class TodoServiceUnavailableError(TodoServiceError):
    error_code = "todo_service_unavailable"
    public_message = "Todo service is temporarily unavailable."