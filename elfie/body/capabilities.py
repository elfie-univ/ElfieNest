"""身体可提供的传感器、动作和安全限制。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping


@dataclass(frozen=True)
class BodyCapabilities:
    """一副身体在建立连接后声明的实际能力。"""

    sensors: FrozenSet[str] = frozenset()
    actions: FrozenSet[str] = frozenset()
    limits: Mapping[str, Any] = field(default_factory=dict)

    def supports_sensor(self, sensor: str) -> bool:
        return "*" in self.sensors or sensor in self.sensors

    def supports_action(self, action: str) -> bool:
        return "*" in self.actions or action in self.actions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensors": sorted(self.sensors),
            "actions": sorted(self.actions),
            "limits": dict(self.limits),
        }
