"""Provider-neutral model boundary owned by Brain."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Mapping, Optional, Protocol, Tuple

from pydantic import AliasChoices, Field, JsonValue, StringConstraints

from elfie.message_types import EventId, FrozenContractModel, TurnId, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]


@unique
class StructuredOutputMode(str, Enum):
    """Single structured-output strategy selected before generation."""

    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"
    JSON_TEXT = "json_text"


class JsonSchemaDocument(FrozenContractModel):
    """Named JSON Schema passed through the orchestration adapter."""

    name: _NonBlankText
    document: Mapping[str, JsonValue] = Field(
        validation_alias=AliasChoices("document", "schema")
    )


class ModelGenerationCapabilities(FrozenContractModel):
    """Known structured-output capabilities for one selected model."""

    provider: _NonBlankText
    model_key: _NonBlankText
    supports_json_schema: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    supports_plain_text: bool
    max_output_tokens: Annotated[int, Field(strict=True, ge=1)]

    @property
    def plain_text_only(self) -> bool:
        """Return whether model output must be treated as inert text."""
        return not (
            self.supports_json_schema
            or self.supports_tool_calling
            or self.supports_json_mode
        )


class ModelGenerationRequest(FrozenContractModel):
    """Complete request from Brain to an application-owned runtime adapter."""

    turn_id: TurnId
    frame_id: EventId
    context_revision: Annotated[int, Field(strict=True, ge=0)]
    capability_revision: Annotated[int, Field(strict=True, ge=0)]
    created_at: UTCDateTime
    deadline: UTCDateTime
    cause_event_ids: Tuple[EventId, ...]
    system_prompt: _NonBlankText
    user_prompt: _NonBlankText
    response_schema: JsonSchemaDocument
    allowed_tools: Tuple[_NonBlankText, ...] = ()
    temperature: Annotated[float, Field(strict=True, ge=0.0, le=2.0)] = 0.2
    max_tokens: Annotated[int, Field(strict=True, ge=1)] = 512


class ModelGenerationResult(FrozenContractModel):
    """Raw model text plus exact generation metadata."""

    text: str
    selected_mode: StructuredOutputMode
    provider: _NonBlankText
    model_key: _NonBlankText
    prompt_tokens: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    completion_tokens: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    latency_ms: Optional[Annotated[float, Field(strict=True, ge=0.0)]] = None

    @property
    def token_count(self) -> Optional[int]:
        """Return total tokens only when both counters are available."""
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens


class ModelPort(Protocol):
    """Provider-neutral model capability required by Brain."""

    def capabilities(self) -> ModelGenerationCapabilities:
        """Return capabilities for the model that will handle the request."""
        ...

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        """Run exactly one primary model generation."""
        ...

    def abandon(self, request: ModelGenerationRequest) -> None:
        """Detach a timed-out request from any runtime serialization lease."""
        ...


__all__ = (
    "ModelPort",
    "JsonSchemaDocument",
    "ModelGenerationCapabilities",
    "ModelGenerationRequest",
    "ModelGenerationResult",
    "StructuredOutputMode",
)
