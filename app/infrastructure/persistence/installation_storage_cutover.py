"""Atomic one-time copy from legacy Setup state into final installation storage."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping

from ai_runtime.storage.config_store import read_yaml_mapping
from app.infrastructure.persistence.legacy_installation_record import (
    LegacyInstallationRecord,
    legacy_installation_record_from_row,
)
from app.infrastructure.persistence.transition_account_schema import (
    ensure_local_installations_schema,
)

_STEP_MAPPING: Final[dict[int, str]] = {
    1: "not_started",
    2: "owner",
    3: "providers",
    4: "nest",
    5: "food",
}
_TASK_STATES: Final[frozenset[str]] = frozenset(
    {"idle", "running", "failed", "completed", "cancelled"}
)


@dataclass(frozen=True)
class InstallationCutoverError(RuntimeError):
    """A legacy installation cannot be represented by current final state."""

    __slots__ = ("reason",)

    reason: str

    def __str__(self) -> str:
        return self.reason


def ensure_installation_storage_cutover(
    connection: sqlite3.Connection,
    *,
    config_path: Path,
) -> None:
    """Create and populate the final singleton once in the active transaction."""
    if _target_exists(connection):
        _freeze_legacy_installation(connection)
        return
    legacy = _read_legacy_installation(connection)
    _validate_legacy_installation(legacy)
    _validate_current_config(legacy, read_yaml_mapping(config_path))
    ensure_local_installations_schema(connection)
    setup_state = _setup_state(legacy)
    setup_step = "food" if setup_state == "completed" else _STEP_MAPPING[
        legacy.current_step
    ]
    connection.execute(
        """
        INSERT INTO local_installations (
            installation_id, owner_user_id, device_name, platform,
            machine_id_hash, setup_state, setup_step, owner_completed_at,
            providers_completed_at, nest_completed_at, food_completed_at,
            completed_at, last_seen_at, active_task_step, active_task_key,
            task_state, task_progress, last_error, updated_at
        ) VALUES (
            'local', ?, 'local', ?, NULL, ?, ?, ?, NULL, ?, NULL, ?, NULL,
            ?, ?, ?, ?, ?, ?
        )
        """,
        (
            legacy.owner_user_id,
            sys.platform,
            setup_state,
            setup_step,
            legacy.owner_completed_at,
            legacy.nest_completed_at,
            legacy.completed_at,
            legacy.active_task_step,
            legacy.active_task_key,
            legacy.task_state,
            legacy.task_progress,
            legacy.last_error,
            legacy.updated_at,
        ),
    )
    _freeze_legacy_installation(connection)


def _target_exists(connection: sqlite3.Connection) -> bool:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
        "AND name = 'local_installations'"
    ).fetchone()
    if table is None:
        return False
    return connection.execute(
        "SELECT 1 FROM local_installations WHERE installation_id = 'local'"
    ).fetchone() is not None


def _read_legacy_installation(
    connection: sqlite3.Connection,
) -> LegacyInstallationRecord:
    row = connection.execute(
        "SELECT * FROM setup_progress WHERE singleton_id = 1"
    ).fetchone()
    if row is None:
        raise InstallationCutoverError("旧 Setup 安装记录缺失，无法复制")
    return legacy_installation_record_from_row(row)


def _validate_current_config(
    legacy: LegacyInstallationRecord,
    config: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> None:
    providers = config.get("providers")
    ollama = providers.get("ollama") if isinstance(providers, dict) else None
    if legacy.ollama_decision in {"bound_existing", "install_official"}:
        configured_endpoint = (
            str(ollama.get("api_base", "")) if isinstance(ollama, dict) else ""
        )
        if not legacy.ollama_endpoint or configured_endpoint != legacy.ollama_endpoint:
            raise InstallationCutoverError(
                "当前配置未表达旧 Setup 的 Ollama endpoint"
            )
    if legacy.model_decision == "configured":
        configured_model = (
            str(ollama.get("selected_model", ""))
            if isinstance(ollama, dict)
            else ""
        )
        if not legacy.model_reference or configured_model != legacy.model_reference:
            raise InstallationCutoverError(
                "当前配置未表达旧 Setup 的 configured model"
            )


def _validate_legacy_installation(legacy: LegacyInstallationRecord) -> None:
    if legacy.current_step not in _STEP_MAPPING:
        raise InstallationCutoverError("旧 Setup 安装记录包含非法 current_step")
    if legacy.task_state not in _TASK_STATES:
        raise InstallationCutoverError("旧 Setup 安装记录包含非法 task_state")
    if legacy.task_progress not in range(0, 101):
        raise InstallationCutoverError("旧 Setup 安装记录包含非法 task_progress")
    active_fields_match = (legacy.active_task_step is None) == (
        legacy.active_task_key is None
    )
    if not active_fields_match:
        raise InstallationCutoverError("旧 Setup 安装记录包含非法 active task")


def _setup_state(legacy: LegacyInstallationRecord) -> str:
    if legacy.completed_at is not None:
        return "completed"
    if (
        legacy.current_step == 1
        and legacy.owner_user_id is None
        and legacy.task_state == "idle"
    ):
        return "not_started"
    return "in_progress"


def _freeze_legacy_installation(connection: sqlite3.Connection) -> None:
    for operation in ("INSERT", "UPDATE", "DELETE"):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS freeze_setup_progress_{operation.lower()}
            BEFORE {operation} ON setup_progress
            BEGIN
                SELECT RAISE(ABORT, 'setup_progress is frozen');
            END
            """
        )
