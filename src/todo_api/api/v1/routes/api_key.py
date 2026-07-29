from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from todo_api.api.deps import APIKeyServiceDep, CurrentUser
from todo_api.api.responses import error_response
from todo_api.exceptions.api_key import (
    APIKeyCreationUnavailableError,
    APIKeyListUnavailableError,
    APIKeyNotFoundError,
    APIKeyRevocationUnavailableError,
)
from todo_api.models.api_key import APIKey
from todo_api.schemas.api_key import (
    APIKeyCreatedResponseSchema,
    APIKeyCreateSchema,
    APIKeyResponseSchema,
)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIKeyCreatedResponseSchema,
    status_code=status.HTTP_201_CREATED,
    description="Returns the plaintext API key once; only its hash is stored.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            APIKeyCreationUnavailableError, description="API key creation is unavailable."
        )
    },
)
async def create_api_key(
    payload: APIKeyCreateSchema,
    service: APIKeyServiceDep,
    current_user: CurrentUser,
) -> APIKeyCreatedResponseSchema:
    return await service.issue(user_id=current_user.id, name=payload.name)


@router.get(
    "",
    response_model=list[APIKeyResponseSchema],
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            APIKeyListUnavailableError,
            description="API key listing is unavailable.",
        )
    },
)
async def get_api_keys(
    service: APIKeyServiceDep,
    current_user: CurrentUser,
    include_revoked: Annotated[bool, Query()] = False,
) -> list[APIKey]:
    return await service.list(user_id=current_user.id, include_revoked=include_revoked)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: error_response(
            APIKeyNotFoundError,
            description="API key was not found.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: error_response(
            APIKeyRevocationUnavailableError, description="API key revocation is unavailable."
        ),
    },
)
async def delete_api_key(
    service: APIKeyServiceDep,
    current_user: CurrentUser,
    api_key_id: Annotated[int, Path(gt=0)],
) -> Response:
    await service.revoke(user_id=current_user.id, api_key_id=api_key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
