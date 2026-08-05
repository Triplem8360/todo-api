from __future__ import annotations

from todo_api.exceptions.base import ApplicationError


class AuthServiceError(ApplicationError):
    error_code = "auth_service_error"
    public_message = "Authentication operation failed."


class EmailAlreadyRegisteredError(AuthServiceError):
    error_code = "email_already_registered"
    public_message = "A user with this email already exists."


class RegistrationUnavailableError(AuthServiceError):
    error_code = "registration_unavailable"
    public_message = "Registration could not be completed."


class InvalidCredentialsError(AuthServiceError):
    error_code = "invalid_credentials"
    public_message = "Incorrect email or password."


class InvalidBasicCredentialsError(InvalidCredentialsError):
    error_code = "invalid_basic_credentials"
    public_message = "Invalid Basic authentication credentials."


class BasicAuthenticationUnavailableError(AuthServiceError):
    error_code = "basic_authentication_unavailable"
    public_message = "Basic authentication could not be completed."


class InactiveUserError(AuthServiceError):
    error_code = "inactive_user"
    public_message = "User account is inactive."


class InvalidAccessTokenError(AuthServiceError):
    error_code = "invalid_access_token"
    public_message = "Access token is invalid or expired."


class InvalidRefreshTokenError(AuthServiceError):
    error_code = "invalid_refresh_token"
    public_message = "Refresh token is invalid or expired."


class InvalidCSRFTokenError(AuthServiceError):
    error_code = "invalid_csrf_token"
    public_message = "CSRF token is missing or invalid."

class RequestOriginNotAllowedError(AuthServiceError):
    error_code = "request_origin_not_allowed"
    public_message = "Request origin is not allowed."


class RefreshTokenReuseDetectedError(InvalidRefreshTokenError):
    error_code = "refresh_token_reuse_detected"
    public_message = "Refresh token reuse was detected. Sign in again."


class LoginSessionUnavailableError(AuthServiceError):
    error_code = "login_session_unavailable"
    public_message = "Login could not be completed."


class TokenAuthenticationUnavailableError(AuthServiceError):
    error_code = "token_authentication_unavailable"
    public_message = "Token authentication could not be completed."


class TokenRefreshUnavailableError(AuthServiceError):
    error_code = "token_refresh_unavailable"
    public_message = "Token refresh could not be completed."


class LogoutUnavailableError(AuthServiceError):
    error_code = "logout_unavailable"
    public_message = "Logout could not be completed."
