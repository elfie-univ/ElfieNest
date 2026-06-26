from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    prompt: str
    energy: float = 100.0
    task_complexity: int = 1
    allowed_tools: tuple[str, ...] = (
        "web_search",
        "code_sandbox",
        "skills_evolution",
    )
    messages: tuple[dict[str, Any], ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    text: str
    mode: str
    model_key: str
    decision: dict[str, Any]
    degraded: bool = False
