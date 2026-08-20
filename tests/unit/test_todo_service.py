from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.models.todo import Todo, TodoPriority
from todo_api.schemas.todo import TodoUpdateSchema
from todo_api.services.todo import TodoService


def test_update_refreshes_server_generated_fields_before_commit() -> None:
    session = AsyncMock(spec=AsyncSession)
    todo = Todo(
        id=1,
        user_id=7,
        title="Load-test this endpoint",
        priority=TodoPriority.MEDIUM,
    )
    service = TodoService(session=session)

    with patch(
        "todo_api.services.todo.get_owned_todo",
        new=AsyncMock(return_value=todo),
    ):
        result = asyncio.run(
            service.update(
                user_id=7,
                todo_id=1,
                payload=TodoUpdateSchema(priority=TodoPriority.HIGH),
            )
        )

    assert result is todo
    assert todo.priority is TodoPriority.HIGH
    session.flush.assert_awaited_once_with()
    session.refresh.assert_awaited_once_with(todo)
    session.commit.assert_awaited_once_with()
