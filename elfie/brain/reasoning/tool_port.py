"""Typed semantic Tool boundary owned by Brain.

Tool definitions describe atomic capabilities and their JSON Schemas.  The
injected ``ToolPort`` performs bounded execution; it never accepts a
filesystem root, SDK object, or provider-specific payload.  Agent Skills are
procedural documents and are intentionally not represented here.
"""

from __future__ import annotations

from typing import Annotated, Literal, Mapping, Optional, Protocol, Tuple

from pydantic import Field, JsonValue, StringConstraints, model_validator

from elfie.message_types import ElfieId, ErrorInfo, FrozenContractModel

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"),
]
ToolKey = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$"
    ),
]
ToolOperation = Literal["search", "read", "list"]


class ToolDefinition(FrozenContractModel):
    """Provider-neutral description of one executable Tool."""

    name: ToolKey
    title: Optional[_NonBlankText] = None
    description: _NonBlankText
    input_schema: Mapping[str, JsonValue]
    output_schema: Optional[Mapping[str, JsonValue]] = None
    side_effect: Literal["none", "external"] = "none"


class ToolCall(FrozenContractModel):
    """One native model Tool call after provider normalization."""

    call_id: _NonBlankText
    tool_key: ToolKey
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)


class ToolRequest(FrozenContractModel):
    """One authorized semantic request for a bounded tool capability."""

    scope_id: Optional[ElfieId] = None
    tool_key: ToolKey
    operation: ToolOperation
    query: Optional[_NonBlankText] = None
    resource_id: Optional[_NonBlankText] = None
    max_results: Annotated[int, Field(strict=True, ge=1, le=10)] = 3

    @model_validator(mode="after")
    def validate_operation(self) -> ToolRequest:
        if self.tool_key == "web_search":
            if self.operation != "search" or self.query is None:
                raise ValueError("web_search requires a query and search operation")
            if self.resource_id is not None:
                raise ValueError("web_search cannot carry a resource_id")
        elif self.operation == "search" or self.query is not None:
            raise ValueError("local_file requires read or list without a query")
        if self.tool_key == "local_file" and self.scope_id is None:
            raise ValueError("local_file requires an Elfie scope")
        if self.operation == "read" and self.resource_id is None:
            raise ValueError("local_file read requires a resource_id")
        return self


class ToolResult(FrozenContractModel):
    """Bounded result returned by a ToolPort implementation."""

    tool_key: ToolKey
    ok: bool
    content: str
    truncated: bool = False
    retained_bytes: Annotated[int, Field(strict=True, ge=0)] = 0
    source_items: Annotated[int, Field(strict=True, ge=0)] = 0
    error: Optional[ErrorInfo] = None

    @model_validator(mode="after")
    def validate_error(self) -> ToolResult:
        if self.ok and self.error is not None:
            raise ValueError("successful tool results cannot carry an error")
        if not self.ok and self.error is None:
            raise ValueError("failed tool results require typed error information")
        return self


class ToolPort(Protocol):
    """Consumer-owned semantic tool capability required by Brain."""

    def available_tool_keys(self) -> Tuple[ToolKey, ...]:
        """Return globally enabled keys for this scoped Elfie view."""
        ...

    def available_tool_definitions(self) -> Tuple[ToolDefinition, ...]:
        """Return model-facing definitions for the same scoped Tool view."""
        ...

    def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one bounded request or return a typed denial/failure."""
        ...


__all__ = (
    "ToolKey",
    "ToolDefinition",
    "ToolCall",
    "ToolOperation",
    "ToolPort",
    "ToolRequest",
    "ToolResult",
)
