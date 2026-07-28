from __future__ import annotations

from pathlib import Path

from todo_api.core.config import Settings


def test_env_example_matches_settings_validation_aliases() -> None:
    env_example = Path(__file__).parents[2] / ".env.example"
    env_keys = {
        line.partition("=")[0]
        for line in env_example.read_text().splitlines()
        if line and not line.startswith("#")
    }
    validation_aliases = {str(field.validation_alias) for field in Settings.model_fields.values()}

    assert env_keys == validation_aliases
