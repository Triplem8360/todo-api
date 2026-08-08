from __future__ import annotations

from todo_api.app import create_app
from todo_api.core.logging import configure_logging

configure_logging()

app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("todo_api.main:app", host="0.0.0.0", port=8000)
