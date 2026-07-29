from __future__ import annotations

from fastapi import APIRouter, Response, status

from todo_api.api.deps import (
    CurrentBasicUser,
    CurrentHeaderAPIKeyUser,
    CurrentQueryAPIKeyUser,
    CurrentUser,
    UserServiceDep,
)
from todo_api.api.responses import error_response
from todo_api.exceptions.user import (
    AccountDeactivationUnavailableError,
    ProfileUpdateUnavailableError,
)
from todo_api.models.user import User
from todo_api.schemas.user import UserProfileUpdateSchema, UserResponseSchema

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponseSchema,
    summary="Get my profile",
)
async def get_current_user(current_user: CurrentUser) -> User:
    """Return the user authenticated by the primary access-token flow."""

    return current_user


@router.patch(
    "/me",
    response_model=UserResponseSchema,
    summary="Update my profile",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            ProfileUpdateUnavailableError,
            description="Profile update is unavailable.",
        )
    },
)
async def update_current_user(
    payload: UserProfileUpdateSchema,
    service: UserServiceDep,
    current_user: CurrentUser,
) -> User:
    return await service.update_profile(current_user, payload)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate my account",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            AccountDeactivationUnavailableError,
            description="Account deactivation is unavailable.",
        )
    },
)
async def deactivate_current_user(
    service: UserServiceDep,
    current_user: CurrentUser,
) -> Response:
    await service.deactivate_account(current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/api-key",
    response_model=UserResponseSchema,
    summary="Get my profile with an API key",
)
async def get_current_api_key_user(current_user: CurrentHeaderAPIKeyUser) -> User:
    """Authenticate with the preferred X-API-Key header transport."""

    return current_user


@router.get(
    "/me/basic",
    response_model=UserResponseSchema,
    summary="Get my profile with Basic authentication",
)
async def get_current_basic_user(current_user: CurrentBasicUser) -> User:
    """Compatibility endpoint for HTTP Basic credentials."""

    return current_user


@router.get(
    "/me/query-api-key",
    response_model=UserResponseSchema,
    summary="Get my profile with a query API key",
    deprecated=True,
)
async def get_current_query_api_key_user(current_user: CurrentQueryAPIKeyUser) -> User:
    """Deprecated compatibility endpoint; URLs can leak API keys."""

    return current_user
