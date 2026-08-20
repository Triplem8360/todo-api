from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.exceptions.todo import (
    TodoNotFoundError,
    TodoServiceUnavailableError,
    TodoStateConflictError,
)
from todo_api.models.todo import Todo, TodoStatus
from todo_api.repositories.todo import (
    create_todo,
    delete_todo,
    get_owned_todo,
    list_owned_todos,
)
from todo_api.schemas.todo import (
    TodoCreateSchema,
    TodoListQuerySchema,
    TodoListResponseSchema,
    TodoResponseSchema,
    TodoUpdateSchema,
)


@dataclass(slots=True)
class TodoService:
    session: AsyncSession

    async def create(
        self,
        user_id: int,
        payload: TodoCreateSchema,
    ) -> Todo:
        try:
            todo = await create_todo(
                self.session,
                user_id=user_id,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                due_at=payload.due_at,
            )
            await self.session.commit()
            return todo
        except SQLAlchemyError as exc:
            raise TodoServiceUnavailableError() from exc

    async def get(
        self,
        user_id: int,
        todo_id: int,
    ) -> Todo:
        try:
            todo = await get_owned_todo(
                self.session,
                user_id=user_id,
                todo_id=todo_id,
            )
        except SQLAlchemyError as exc:
            raise TodoServiceUnavailableError() from exc

        if todo is None:
            raise TodoNotFoundError()

        return todo

    async def list(
        self,
        user_id: int,
        query: TodoListQuerySchema,
    ) -> TodoListResponseSchema:
        try:
            items, total = await list_owned_todos(
                self.session,
                user_id=user_id,
                search=query.q,
                status=query.status,
                priority=query.priority,
                is_archived=query.is_archived,
                due_from=query.due_from,
                due_to=query.due_to,
                sort_by=query.sort_by,
                sort_direction=query.sort_direction,
                limit=query.limit,
                offset=query.offset,
            )
        except SQLAlchemyError as exc:
            raise TodoServiceUnavailableError() from exc

        return TodoListResponseSchema(
            items=[TodoResponseSchema.model_validate(todo) for todo in items],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    async def update(
        self,
        user_id: int,
        todo_id: int,
        payload: TodoUpdateSchema,
    ) -> Todo:
        try:
            todo = await get_owned_todo(
                self.session,
                user_id=user_id,
                todo_id=todo_id,
                for_update=True,
            )

            if todo is None:
                raise TodoNotFoundError()

            changes = payload.model_dump(exclude_unset=True)
            requested_status = changes.pop("status", None)

            for field, value in changes.items():
                setattr(todo, field, value)

            if requested_status is not None:
                self._transition(todo, requested_status)

            await self.session.flush()
            await self.session.refresh(todo)
            await self.session.commit()
            return todo
        except (TodoNotFoundError, TodoStateConflictError):
            raise
        except SQLAlchemyError as exc:
            raise TodoServiceUnavailableError() from exc

    async def delete(
        self,
        user_id: int,
        todo_id: int,
    ) -> None:
        try:
            todo = await get_owned_todo(
                self.session,
                user_id=user_id,
                todo_id=todo_id,
                for_update=True,
            )

            if todo is None:
                raise TodoNotFoundError()

            await delete_todo(self.session, todo)
            await self.session.commit()
        except TodoNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise TodoServiceUnavailableError() from exc

    @staticmethod
    def _transition(todo: Todo, target: TodoStatus) -> None:
        if target is todo.status:
            return

        if todo.status is TodoStatus.CANCELLED and target is not TodoStatus.TODO:
            raise TodoStateConflictError()

        if todo.status is TodoStatus.DONE and target is TodoStatus.CANCELLED:
            raise TodoStateConflictError()

        match target:
            case TodoStatus.TODO:
                todo.reopen()

            case TodoStatus.IN_PROGRESS:
                todo.status = TodoStatus.IN_PROGRESS
                todo.completed_at = None

            case TodoStatus.DONE:
                try:
                    todo.complete()
                except ValueError as exc:
                    raise TodoStateConflictError() from exc

            case TodoStatus.CANCELLED:
                todo.cancel()
