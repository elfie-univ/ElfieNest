"""身体可提供的传感器、动作和安全限制。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, cast

from pydantic import JsonValue


@dataclass(frozen=True)
class BodyCapabilities:
    """一副身体在建立连接后声明的实际能力。"""

    sensors: FrozenSet[str] = frozenset()
    actions: FrozenSet[str] = frozenset()
    limits: Mapping[str, JsonValue] = field(default_factory=dict)
    revision: int = 1

    def supports_sensor(self, sensor: str) -> bool:
        return "*" in self.sensors or sensor in self.sensors

    def supports_action(self, action: str) -> bool:
        if "*" in self.actions or action in self.actions:
            return True
        aliases = {
            "speech.say": "body.speak",
            "move_to_anchor": "body.move_to_anchor",
            "system.emergency_stop": "body.emergency_stop",
        }
        alias = aliases.get(action)
        if alias is not None and alias in self.actions:
            return True
        return action.startswith("expression.") and "body.expression" in self.actions

    def to_dict(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "sensors": sorted(self.sensors),
                "actions": sorted(self.actions),
                "limits": dict(self.limits),
                "revision": self.revision,
            },
        )
