"""Compensate runtime config when a Setup milestone transaction rejects."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.features.setup.progress import complete_setup_step


def complete_configured_setup_step(
    *,
    restore_config: Callable[[dict[str, Any]], None],
    previous_config: dict[str, Any],
    config_snapshot: Mapping[str, Any],
    db_path: str,
    step: int,
    decision: str,
    ollama_endpoint: str | None = None,
    model_reference: str | None = None,
) -> None:
    try:
        complete_setup_step(
            db_path,
            step=step,
            decision=decision,
            ollama_endpoint=ollama_endpoint,
            model_reference=model_reference,
            config_snapshot=config_snapshot,
        )
    except Exception:
        restore_config(previous_config)
        raise
