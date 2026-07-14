from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    prompt: str
    energy: float = 100.0
    task_complexity: int = 1
    allowed_tools: tuple[str, ...] = (
        "web_search",
        "local_file",
        "code_sandbox",
        "skills_evolution",
    )
    messages: tuple[dict[str, Any], ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()
    elfie_id: str | None = None
    food_key: str | None = None
    scene: str = "chat"


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    text: str
    mode: str
    model_key: str
    decision: dict[str, Any]
    degraded: bool = False
    food_requested: str | None = None
    food_used: str | None = None
    execution_stage: str | None = None
    actual_model: str | None = None
    food_clamped: bool = False
