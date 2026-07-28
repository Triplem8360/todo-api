from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def get_violated_constraint_name(
    error: IntegrityError,
) -> str | None:
    """Extract the violated constraint name from a DBAPI error."""

    original_error = error.orig

    candidates = (
        original_error,
        getattr(original_error, "__cause__", None),
    )

    for candidate in candidates:
        if candidate is None:
            continue

        constraint_name = getattr(
            candidate,
            "constraint_name",
            None,
        )

        if isinstance(constraint_name, str):
            return constraint_name

        diagnostic = getattr(
            candidate,
            "diag",
            None,
        )

        constraint_name = getattr(
            diagnostic,
            "constraint_name",
            None,
        )

        if isinstance(constraint_name, str):
            return constraint_name

    return None


def is_constraint_violation(
    error: IntegrityError,
    constraint_name: str,
) -> bool:
    """Return whether a specific database constraint was violated."""

    return get_violated_constraint_name(error) == constraint_name
