"""Explicit registry of the built-in Tools exposed to model adapters."""

from __future__ import annotations

from threading import RLock
from typing import Dict, List, Optional, Tuple

from elfie.brain.reasoning.tool_port import ToolDefinition

BUILTIN_TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="web_search",
        title="Web search",
        description="Search the public web and return bounded source snippets.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 8192},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "truncated": {"type": "boolean"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    ),
    ToolDefinition(
        name="local_file",
        title="Local file",
        description="Read or list files within the current Elfie workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["read", "list"]},
                "resource_id": {"type": "string", "minLength": 1, "maxLength": 8192},
            },
            "required": ["operation", "resource_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "truncated": {"type": "boolean"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    ),
)


class ToolRegistrationError(ValueError):
    """Raised when an explicit Tool definition is invalid or duplicated."""


class ToolRegistry:
    """Thread-safe explicit Tool catalog; it never scans or imports directories."""

    def __init__(
        self, definitions: Tuple[ToolDefinition, ...] = BUILTIN_TOOL_DEFINITIONS
    ):
        self._definitions: Dict[str, ToolDefinition] = {}
        self._lock = RLock()
        for definition in definitions:
            self.register(definition)

    def register(
        self, definition: ToolDefinition, *, replace: bool = False
    ) -> ToolDefinition:
        with self._lock:
            existing = self._definitions.get(definition.name)
            if existing is not None and existing != definition and not replace:
                raise ToolRegistrationError(
                    f"Tool already registered: {definition.name}"
                )
            self._definitions[definition.name] = definition
        return definition

    def get(self, name: str) -> Optional[ToolDefinition]:
        with self._lock:
            return self._definitions.get(name)

    def list_definitions(self) -> List[ToolDefinition]:
        with self._lock:
            return list(self._definitions.values())


__all__ = (
    "BUILTIN_TOOL_DEFINITIONS",
    "ToolRegistrationError",
    "ToolRegistry",
)
