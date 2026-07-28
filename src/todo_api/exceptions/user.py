from __future__ import annotations

from todo_api.exceptions.base import ApplicationError


class UserServiceError(ApplicationError):
    error_code = "user_service_error"
    public_message = "User operation could not be completed."


class ProfileUpdateUnavailableError(UserServiceError):
    error_code = "profile_update_unavailable"
    public_message = "Profile update could not be completed."


class AccountDeactivationUnavailableError(UserServiceError):
    error_code = "account_deactivation_unavailable"
    public_message = "Account deactivation could not be completed."
