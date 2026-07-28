from __future__ import annotations

from todo_api.exceptions.base import ApplicationError


class APIKeyServiceError(ApplicationError):
    error_code = "api_key_service_error"
    public_message = "API key operation could not be completed."


class APIKeyRequiredError(APIKeyServiceError):
    error_code = "api_key_required"
    public_message = "API key is required."


class InvalidAPIKeyError(APIKeyServiceError):
    error_code = "invalid_api_key"
    public_message = "API key is invalid or revoked."


class APIKeyCreationUnavailableError(APIKeyServiceError):
    error_code = "api_key_creation_unavailable"
    public_message = "API key creation could not be completed."


class APIKeyListUnavailableError(APIKeyServiceError):
    error_code = "api_key_list_unavailable"
    public_message = "API keys could not be retrieved."


class APIKeyNotFoundError(APIKeyServiceError):
    error_code = "api_key_not_found"
    public_message = "API key was not found."


class APIKeyRevocationUnavailableError(APIKeyServiceError):
    error_code = "api_key_revocation_unavailable"
    public_message = "API key revocation could not be completed."
