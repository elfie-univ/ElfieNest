from __future__ import annotations

import os
import stat
from pathlib import Path

from app.features.configuration.user_config import (
    read_env_file,
    read_user_config,
    write_env_file,
    write_user_config,
)


def test_read_user_config_returns_empty_for_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    assert read_user_config(config_path) == {}


def test_write_user_config_round_trips_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = {
        "system": {
            "adoption": {
                "max_elfies_per_user": 3,
                "default_personality_style": "活泼好动",
            }
        }
    }

    write_user_config(config, config_path)

    assert read_user_config(config_path) == config
    if os.name == "posix":
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_read_env_file_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n# comment\nOPENAI_API_KEY=sk-test\n QWEN_API_KEY = qwen-test \n",
        encoding="utf-8",
    )

    assert read_env_file(env_path) == {
        "OPENAI_API_KEY": "sk-test",
        "QWEN_API_KEY": "qwen-test",
    }


def test_write_env_file_uses_owner_only_permissions(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    write_env_file({"QWEN_API_KEY": "qwen-test"}, env_path)

    assert read_env_file(env_path) == {"QWEN_API_KEY": "qwen-test"}
    if os.name == "posix":
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == 0o600


def test_default_user_config_and_env_use_final_paths(
    monkeypatch, tmp_path: Path
) -> None:
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    # When
    write_user_config({"system": {"enabled": True}})
    write_env_file({"OPENAI_API_KEY": "local-secret"})

    # Then
    assert read_user_config() == {"system": {"enabled": True}}
    assert read_env_file() == {"OPENAI_API_KEY": "local-secret"}
    assert (tmp_path / "configs" / "runtime.yaml").is_file()
    assert (tmp_path / "configs" / "auth.env").is_file()
