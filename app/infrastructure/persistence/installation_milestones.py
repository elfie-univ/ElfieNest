"""Final Setup milestone updates within a repository-owned transaction."""

from __future__ import annotations

import sqlite3
from typing import Protocol

from app.infrastructure.persistence.installation_record import (
    InstallationRecord,
    installation_step_states,
)


class _MilestoneHandler(Protocol):
    def __call__(
        self,
        connection: sqlite3.Connection,
        record: InstallationRecord,
        decision: str | None,
        model_reference: str | None,
        ollama_endpoint: str | None,
        /,
    ) -> None:
        ...


def complete_installation_milestone(
    connection: sqlite3.Connection,
    record: InstallationRecord,
    *,
    step: int,
    decision: str | None,
    model_reference: str | None,
    ollama_endpoint: str | None,
) -> None:
    """Validate API inputs and dispatch one wizard milestone."""
    handlers: dict[int, _MilestoneHandler] = {
        2: _complete_providers,
        3: _complete_nest,
        4: _complete_food,
        5: _complete_setup,
    }
    handler = handlers.get(step)
    if handler is None:
        raise ValueError("只能通过 Owner 创建完成第一步")
    handler(connection, record, decision, model_reference, ollama_endpoint)


def _complete_providers(
    connection: sqlite3.Connection,
    _record: InstallationRecord,
    decision: str | None,
    _model_reference: str | None,
    ollama_endpoint: str | None,
) -> None:
    if decision not in {"bound_existing", "install_official", "skipped"}:
        raise ValueError("Ollama 步骤需要明确选择")
    if decision != "skipped" and not ollama_endpoint:
        raise ValueError("Ollama 绑定必须保存固定 endpoint")
    _write_completed_milestone(
        connection,
        "setup_step = 'providers', "
        "providers_completed_at = COALESCE(providers_completed_at, CURRENT_TIMESTAMP)",
    )


def _complete_nest(
    connection: sqlite3.Connection,
    _record: InstallationRecord,
    _decision: str | None,
    _model_reference: str | None,
    _ollama_endpoint: str | None,
) -> None:
    _write_completed_milestone(
        connection,
        "setup_step = 'nest', "
        "nest_completed_at = COALESCE(nest_completed_at, CURRENT_TIMESTAMP)",
    )


def _complete_food(
    connection: sqlite3.Connection,
    _record: InstallationRecord,
    decision: str | None,
    model_reference: str | None,
    _ollama_endpoint: str | None,
) -> None:
    if decision not in {"configured", "skipped"}:
        raise ValueError("模型步骤需要明确选择或跳过")
    if decision == "configured" and not model_reference:
        raise ValueError("模型步骤需要保存完整模型引用")
    _write_completed_milestone(
        connection,
        "setup_step = 'food', "
        "food_completed_at = COALESCE(food_completed_at, CURRENT_TIMESTAMP)",
    )


def _complete_setup(
    connection: sqlite3.Connection,
    record: InstallationRecord,
    _decision: str | None,
    _model_reference: str | None,
    _ollama_endpoint: str | None,
) -> None:
    if not all(installation_step_states(record)[:4]):
        raise ValueError("前四步尚未完成，不能结束 Setup")
    connection.execute(
        """
        UPDATE local_installations
        SET setup_state = 'completed', setup_step = 'food',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            active_task_step = NULL, active_task_key = NULL,
            task_state = 'completed', task_progress = 100,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE installation_id = 'local'
        """
    )


def _write_completed_milestone(
    connection: sqlite3.Connection,
    assignment: str,
) -> None:
    connection.execute(
        f"""
        UPDATE local_installations SET setup_state = 'in_progress', {assignment},
            active_task_step = NULL, active_task_key = NULL,
            task_state = 'completed', task_progress = 100,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE installation_id = 'local'
        """
    )
