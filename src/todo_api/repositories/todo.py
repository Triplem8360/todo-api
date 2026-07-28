from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from todo_api.models.todo import Todo, TodoPriority, TodoStatus
from todo_api.schemas.todo import SortDirection, TodoSortField


def _escape_like(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _filters(
    *,
    user_id: int,
    search: str | None,
    status: TodoStatus | None,
    priority: TodoPriority | None,
    is_archived: bool,
    due_from: datetime | None,
    due_to: datetime | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        Todo.user_id == user_id,
        Todo.is_archived.is_(is_archived),
    ]

    if search:
        pattern = f"%{_escape_like(search)}%"
        conditions.append(
            or_(
                Todo.title.ilike(pattern, escape="\\"),
                Todo.description.ilike(pattern, escape="\\"),
            )
        )

    if status is not None:
        conditions.append(Todo.status == status)

    if priority is not None:
        conditions.append(Todo.priority == priority)

    if due_from is not None:
        conditions.append(Todo.due_at >= due_from)

    if due_to is not None:
        conditions.append(Todo.due_at <= due_to)

    return conditions


def _apply_ordering(
    statement: Select[tuple[Todo]],
    *,
    sort_by: TodoSortField,
    sort_direction: SortDirection,
) -> Select[tuple[Todo]]:
    column = {
        TodoSortField.CREATED_AT: Todo.created_at,
        TodoSortField.UPDATED_AT: Todo.updated_at,
        TodoSortField.DUE_AT: Todo.due_at,
        TodoSortField.TITLE: Todo.title,
    }[sort_by]

    order = (
        column.asc()
        if sort_direction == SortDirection.ASC
        else column.desc()
    )

    if sort_by == TodoSortField.DUE_AT:
        order = order.nulls_last()

    id_order = (
        Todo.id.asc()
        if sort_direction == SortDirection.ASC
        else Todo.id.desc()
    )

    return statement.order_by(order, id_order)


async def create_todo(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    description: str | None,
    priority: TodoPriority,
    due_at: datetime | None,
) -> Todo:
    todo = Todo(
        user_id=user_id,
        title=title,
        description=description,
        priority=priority,
        due_at=due_at,
    )

    session.add(todo)
    await session.flush()

    return todo


async def get_owned_todo(
    session: AsyncSession,
    *,
    user_id: int,
    todo_id: int,
    for_update: bool = False,
) -> Todo | None:
    statement = select(Todo).where(
        Todo.id == todo_id,
        Todo.user_id == user_id,
    )

    if for_update:
        statement = statement.with_for_update()

    return await session.scalar(statement)


async def list_owned_todos(
    session: AsyncSession,
    *,
    user_id: int,
    search: str | None,
    status: TodoStatus | None,
    priority: TodoPriority | None,
    is_archived: bool,
    due_from: datetime | None,
    due_to: datetime | None,
    sort_by: TodoSortField,
    sort_direction: SortDirection,
    limit: int,
    offset: int,
) -> tuple[Sequence[Todo], int]:
    conditions = _filters(
        user_id=user_id,
        search=search,
        status=status,
        priority=priority,
        is_archived=is_archived,
        due_from=due_from,
        due_to=due_to,
    )

    items_statement = _apply_ordering(
        select(Todo).where(*conditions),
        sort_by=sort_by,
        sort_direction=sort_direction,
    ).limit(limit).offset(offset)

    count_statement = (
        select(func.count())
        .select_from(Todo)
        .where(*conditions)
    )

    items = (await session.scalars(items_statement)).all()
    total = int(await session.scalar(count_statement) or 0)

    return items, total


async def delete_todo(
    session: AsyncSession,
    todo: Todo,
) -> None:
    await session.delete(todo)