"""Memory algorithms consume one narrow, Food-aware model Port."""

from __future__ import annotations

from typing import Protocol


class MemoryModelPort(Protocol):
    """Narrow semantic text-generation capability used by memory algorithms."""

    def ask_with_food(
        self,
        prompt: str,
        *,
        food_key: str | None,
        elfie_id: str | None,
        scene: str,
        semantic_role: str,
        energy: float,
        task_complexity: int,
        allowed_skills: list[str] | None,
    ) -> str: ...


def ask_memory_model(
    model_port: MemoryModelPort,
    prompt: str,
    *,
    elfie_id: str | None,
    semantic_role: str,
    complexity: int,
) -> str:
    return model_port.ask_with_food(
        prompt=prompt,
        food_key=None,
        elfie_id=elfie_id,
        scene="memory",
        semantic_role=semantic_role,
        energy=50.0,
        task_complexity=complexity,
        allowed_skills=[],
    )


__all__ = ("MemoryModelPort", "ask_memory_model")
