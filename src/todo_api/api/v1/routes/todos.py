from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from todo_api.api.deps import (
    CurrentAuthorizationCodeUser,
    CurrentBearerUser,
    TodoServiceDep,
    require_csrf_token,
    validate_request_origin,
)
from todo_api.api.responses import error_response
from todo_api.exceptions.auth import (
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCSRFTokenError,
    RequestOriginNotAllowedError,
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


_UNAUTHORIZED_RESPONSE = error_response(
    InvalidAccessTokenError,
    description="Access token is invalid or expired.",
    authenticate="Bearer",
)

_AUTH_FORBIDDEN_RESPONSE = error_response(
    InactiveUserError,
    description="The authenticated user is not allowed to access this resource.",
)

_BROWSER_WRITE_FORBIDDEN_RESPONSE = error_response(
    InactiveUserError,
    InvalidCSRFTokenError,
    RequestOriginNotAllowedError,
    description=(
        "The browser request was rejected because the account is inactive, "
        "the CSRF token is invalid, or the request origin is not allowed."
    ),
)

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_RESPONSE,
    status.HTTP_403_FORBIDDEN: _AUTH_FORBIDDEN_RESPONSE,
}

_BROWSER_WRITE_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_RESPONSE,
    status.HTTP_403_FORBIDDEN: _BROWSER_WRITE_FORBIDDEN_RESPONSE,
}

_UNAVAILABLE_RESPONSE = error_response(
    TodoServiceUnavailableError,
    description="Todo service is unavailable.",
)

_BROWSER_WRITE_DEPENDENCIES = [
    Depends(validate_request_origin),
    Depends(require_csrf_token),
]


@router.post(
    "",
    response_model=TodoResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_BROWSER_WRITE_AUTH_RESPONSES,
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
    dependencies=_BROWSER_WRITE_DEPENDENCIES,
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
    current_user: CurrentAuthorizationCodeUser,
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
    dependencies=[Depends(require_csrf_token)],
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
        **_BROWSER_WRITE_AUTH_RESPONSES,
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
    dependencies=_BROWSER_WRITE_DEPENDENCIES,
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
        **_BROWSER_WRITE_AUTH_RESPONSES,
        status.HTTP_404_NOT_FOUND: error_response(
            TodoNotFoundError,
            description="Todo does not exist.",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: _UNAVAILABLE_RESPONSE,
    },
    dependencies=_BROWSER_WRITE_DEPENDENCIES,
)
async def remove_todo(
    todo_id: TodoId,
    service: TodoServiceDep,
    current_user: CurrentBearerUser,
) -> Response:
    await service.delete(current_user.id, todo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
