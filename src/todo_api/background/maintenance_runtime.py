from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from todo_api.db.session import Database

MaintenanceOperation = Callable[[Database], Awaitable[int]]
DatabaseFactory = Callable[[], Database]


class MaintenanceWorkerRuntime:
    """Own one async runtime and database per Celery worker process."""

    def __init__(self, database_factory: DatabaseFactory) -> None:
        self._database_factory = database_factory
        self._runner: asyncio.Runner | None = None
        self._database: Database | None = None

    def initialize(self) -> None:
        """Create the event loop after Celery has forked the worker process."""

        if self._runner is not None:
            return

        runner = asyncio.Runner()
        runner.get_loop()
        self._runner = runner

    async def _execute(self, operation: MaintenanceOperation) -> int:
        if self._database is None:
            self._database = self._database_factory()

        return await operation(self._database)

    def run(self, operation: MaintenanceOperation) -> int:
        """Run an operation on the process-owned loop and database engine."""

        self.initialize()
        if self._runner is None:  # pragma: no cover - initialize guarantees this
            raise RuntimeError("The maintenance worker runtime is not initialized.")

        return self._runner.run(self._execute(operation))

    def shutdown(self) -> None:
        """Dispose the database on its owning loop and close that loop."""

        runner = self._runner
        database = self._database
        self._runner = None
        self._database = None

        if runner is None:
            return

        try:
            if database is not None:
                runner.run(database.dispose())
        finally:
            runner.close()
