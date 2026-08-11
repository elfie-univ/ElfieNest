"""Tool-owned observation port and records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Union

ToolMetadataValue = Union[str, int, bool]


@dataclass(frozen=True)
class ToolCallObservation:
    tool_name: str
    ok: bool
    metadata: Mapping[str, ToolMetadataValue] = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionDecisionObservation:
    action: str
    resource: str
    allowed: bool
    mode: str
    reason: str


class ToolObservationPort(Protocol):
    def record_tool_observation(self, observation: ToolCallObservation) -> None: ...

    def record_permission_observation(
        self, observation: PermissionDecisionObservation
    ) -> None: ...


__all__ = (
    "PermissionDecisionObservation",
    "ToolCallObservation",
    "ToolMetadataValue",
    "ToolObservationPort",
)
