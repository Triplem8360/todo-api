from __future__ import annotations

import uvicorn

from todo_api.app import create_app

app = create_app()


def run() -> None:
    uvicorn.run("todo_api.main:app", host="0.0.0.0", port=8000)
