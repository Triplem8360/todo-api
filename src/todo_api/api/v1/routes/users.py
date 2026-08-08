from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Response, status

from todo_api.api.deps import (
    CurrentAuthorizationCodeUser,
    CurrentBasicUser,
    CurrentHeaderAPIKeyUser,
    CurrentQueryAPIKeyUser,
    CurrentUser,
    UserServiceDep,
)
from todo_api.api.responses import error_response
from todo_api.background.request_tasks import record_activity
from todo_api.exceptions.user import (
    AccountDeactivationUnavailableError,
    ProfileUpdateUnavailableError,
)
from todo_api.schemas.user import UserProfileUpdateSchema, UserResponseSchema

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponseSchema,
    summary="Get my profile",
)
async def get_current_user(current_user: CurrentAuthorizationCodeUser) -> UserResponseSchema:
    """Return the user authenticated by the primary access-token flow."""

    return UserResponseSchema.model_validate(current_user)


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
) -> UserResponseSchema:
    updated_user = await service.update_profile(current_user, payload)
    return UserResponseSchema.model_validate(updated_user)


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
    background_tasks: BackgroundTasks,
) -> Response:
    user_id = current_user.id
    await service.deactivate_account(current_user)
    background_tasks.add_task(
        record_activity,
        "user.deactivated",
        user_id=user_id,
        resource_type="user",
        resource_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/api-key",
    response_model=UserResponseSchema,
    summary="Get my profile with an API key",
)
async def get_current_api_key_user(current_user: CurrentHeaderAPIKeyUser) -> UserResponseSchema:
    """Authenticate with the preferred X-API-Key header transport."""

    return UserResponseSchema.model_validate(current_user)


@router.get(
    "/me/basic",
    response_model=UserResponseSchema,
    summary="Get my profile with Basic authentication",
)
async def get_current_basic_user(current_user: CurrentBasicUser) -> UserResponseSchema:
    """Compatibility endpoint for HTTP Basic credentials."""

    return UserResponseSchema.model_validate(current_user)


@router.get(
    "/me/query-api-key",
    response_model=UserResponseSchema,
    summary="Get my profile with a query API key",
    deprecated=True,
)
async def get_current_query_api_key_user(
    current_user: CurrentQueryAPIKeyUser,
) -> UserResponseSchema:
    """Deprecated compatibility endpoint; URLs can leak API keys."""

    return UserResponseSchema.model_validate(current_user)
