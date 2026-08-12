"""Tool-owned observation port and records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Union

from infrastructure.models.runtime_ports import (
    ToolCallObservationPortModel,
    ToolPermissionObservationPortModel,
)

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
    def record_tool_observation(
        self, observation: ToolCallObservationPortModel
    ) -> None: ...

    def record_permission_observation(
        self, observation: ToolPermissionObservationPortModel
    ) -> None: ...


__all__ = (
    "PermissionDecisionObservation",
    "ToolCallObservation",
    "ToolMetadataValue",
    "ToolObservationPort",
)
