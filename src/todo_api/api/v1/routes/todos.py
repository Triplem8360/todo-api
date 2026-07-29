from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response, status

from todo_api.api.deps import CurrentBearerUser, TodoServiceDep
from todo_api.api.responses import error_response
from todo_api.exceptions.auth import (
    InactiveUserError,
    InvalidAccessTokenError,
)
from todo_api.exceptions.todo import (
    TodoNotFoundError,
    TodoServiceUnavailableError,
    TodoStateConflictError,
)
from todo_api.models.todo import Todo
from todo_api.schemas.todo import (
    TodoCreateSchema,
    TodoListQuerySchema,
    TodoListResponseSchema,
    TodoResponseSchema,
    TodoUpdateSchema,
)

router = APIRouter(prefix="/todos", tags=["Todos"])

TodoId = Annotated[int, Path(gt=0)]
TodoQuery = Annotated[TodoListQuerySchema, Query()]

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: error_response(
        InvalidAccessTokenError,
        description="Access token is invalid.",
        authenticate="Bearer",
    ),
    status.HTTP_403_FORBIDDEN: error_response(
        InactiveUserError,
        description="Account is inactive.",
    ),
}

_UNAVAILABLE_RESPONSE = error_response(
    TodoServiceUnavailableError,
    description="Todo service is unavailable.",
)


@router.post(
    "",
    response_model=TodoResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
)
async def create_todo(
    payload: TodoCreateSchema,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> Todo:
    return await service.create(current_user.id, payload)


@router.get(
    "",
    response_model=TodoListResponseSchema,
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
)
async def list_todos(
    query: TodoQuery,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> TodoListResponseSchema:
    return await service.list(current_user.id, query)


@router.get(
    "/{todo_id}",
    response_model=TodoResponseSchema,
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_404_NOT_FOUND: error_response(
            TodoNotFoundError,
            description="Todo does not exist.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
)
async def get_todo(
    todo_id: TodoId,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> Todo:
    return await service.get(current_user.id, todo_id)


@router.patch(
    "/{todo_id}",
    response_model=TodoResponseSchema,
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_404_NOT_FOUND: error_response(
            TodoNotFoundError,
            description="Todo does not exist.",
        ),
        status.HTTP_409_CONFLICT: error_response(
            TodoStateConflictError,
            description="Todo status transition is not allowed.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
)
async def update_todo(
    todo_id: TodoId,
    payload: TodoUpdateSchema,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> Todo:
    return await service.update(current_user.id, todo_id, payload)


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **_AUTH_RESPONSES,
        status.HTTP_404_NOT_FOUND: error_response(
            TodoNotFoundError,
            description="Todo does not exist.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
)
async def remove_todo(
    todo_id: TodoId,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> Response:
    await service.delete(current_user.id, todo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
