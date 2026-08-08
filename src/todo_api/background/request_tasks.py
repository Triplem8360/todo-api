from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_activity(
    event: str,
    *,
    user_id: int,
    resource_type: str | None = None,
    resource_id: int | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record a best-effort application activity after the response is sent."""

    logger.info(
        "application_activity event=%s user_id=%s resource_type=%s resource_id=%s metadata=%s",
        event,
        user_id,
        resource_type,
        resource_id,
        metadata or {},
        extra={
            "activity_event": event,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {},
        },
    )
