from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Annotated, Any, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]


@dataclass(frozen=True)
class RuntimeRequest:
    prompt: str
    energy: float = 100.0
    task_complexity: int = 1
    allowed_tools: tuple[str, ...] = (
        "web_search",
        "local_file",
    )
    messages: tuple[dict[str, Any], ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()
    elfie_id: str | None = None
    food_key: str | None = None
    semantic_role: str = "primary"
    scene: str = "chat"
    images: tuple[str, ...] = ()
    audio: str | None = None


@dataclass(frozen=True)
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


class _FrozenRuntimeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


@unique
class StructuredGenerationMode(str, Enum):
    """Runtime wire strategy selected by the orchestration adapter."""

    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"
    JSON_TEXT = "json_text"


class StructuredMessage(_FrozenRuntimeModel):
    """One typed text message accepted by the runtime gateway."""

    role: _NonBlankText
    content: _NonBlankText


class StructuredRuntimeCapabilities(_FrozenRuntimeModel):
    """Known structured-output support for one runtime target."""

    provider: _NonBlankText
    model_key: _NonBlankText
    supports_json_schema: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    supports_plain_text: bool
    max_output_tokens: Annotated[int, Field(strict=True, ge=1)]


class StructuredRuntimeRequest(_FrozenRuntimeModel):
    """Typed structured generation request at the Runtime boundary."""

    prompt: _NonBlankText
    messages: Tuple[StructuredMessage, ...]
    response_schema_name: _NonBlankText
    response_schema: Mapping[str, JsonValue]
    selected_mode: StructuredGenerationMode
    allowed_tools: Tuple[_NonBlankText, ...]
    provider: Optional[_NonBlankText] = None
    model_key: Optional[_NonBlankText] = None
    food_key: Optional[_NonBlankText] = None
    food_unavailable: bool = False
    scope_id: Optional[_NonBlankText] = None
    temperature: Annotated[float, Field(strict=True, ge=0.0, le=2.0)] = 0.2
    max_tokens: Annotated[int, Field(strict=True, ge=1)] = 512

    def to_result(
        self,
        *,
        text: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
    ) -> StructuredRuntimeResult:
        """Build a result for adapters and deterministic runtime fakes."""
        return StructuredRuntimeResult(
            text=text,
            selected_mode=self.selected_mode,
            provider=self.provider or "unknown",
            model_key=self.model_key or "unknown",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )


class StructuredRuntimeResult(_FrozenRuntimeModel):
    """Raw structured-generation response and provider metadata."""

    text: str
    selected_mode: StructuredGenerationMode
    provider: _NonBlankText
    model_key: _NonBlankText
    prompt_tokens: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    completion_tokens: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    latency_ms: Optional[Annotated[float, Field(strict=True, ge=0.0)]] = None


__all__ = (
    "RuntimeRequest",
    "RuntimeResult",
    "StructuredGenerationMode",
    "StructuredMessage",
    "StructuredRuntimeCapabilities",
    "StructuredRuntimeRequest",
    "StructuredRuntimeResult",
)
