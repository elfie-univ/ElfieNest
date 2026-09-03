"""身体可提供的传感器、动作和安全限制。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Tuple, cast

from pydantic import JsonValue


@dataclass(frozen=True)
class BodyCapabilityDescriptor:
    """一个由具体 Body Adapter 注册的、可枚举的动作能力。"""

    capability_id: str
    description: str | None = None
    argument_schema: Mapping[str, JsonValue] = field(default_factory=dict)
    model_visible: bool = True

    def to_dict(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "capability_id": self.capability_id,
                "description": self.description,
                "argument_schema": dict(self.argument_schema),
                "model_visible": self.model_visible,
            },
        )


@dataclass(frozen=True)
class BodyCapabilities:
    """一副身体在建立连接后声明的实际能力。

    ``sensors``/``actions`` 保留为运行时快速判断和旧适配器的输入；新适配器应同时
    注册带参数 Schema 的 descriptor。Brain 不复制这份事实，只读取它的投影。
    """

    sensors: FrozenSet[str] = frozenset()
    actions: FrozenSet[str] = frozenset()
    limits: Mapping[str, JsonValue] = field(default_factory=dict)
    revision: int = 1
    action_catalog: Tuple[BodyCapabilityDescriptor, ...] = ()
    input_catalog: Tuple[BodyCapabilityDescriptor, ...] = ()

    def list_actions(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]:
        """返回当前动作目录；未升级的适配器从旧 action 集合生成无 Schema 描述。"""
        descriptors = self.action_catalog or tuple(
            BodyCapabilityDescriptor(capability_id=action)
            for action in sorted(self.actions)
        )
        if model_visible:
            descriptors = tuple(item for item in descriptors if item.model_visible)
        return descriptors

    def list_inputs(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]:
        """返回当前输入目录；旧适配器同样可以通过 sensors 自动投影。"""
        descriptors = self.input_catalog or tuple(
            BodyCapabilityDescriptor(capability_id=sensor)
            for sensor in sorted(self.sensors)
        )
        if model_visible:
            descriptors = tuple(item for item in descriptors if item.model_visible)
        return descriptors

    def register_action(self, descriptor: BodyCapabilityDescriptor) -> BodyCapabilities:
        """返回注册后的新快照；注册发生在 Adapter/Body 装配侧。"""
        if not descriptor.capability_id.strip():
            raise ValueError("body capability ID must not be blank")
        current = {item.capability_id: item for item in self.list_actions()}
        action_ids = set(self.actions) | set(current)
        if current.get(descriptor.capability_id) == descriptor:
            return self
        current[descriptor.capability_id] = descriptor
        action_ids.add(descriptor.capability_id)
        return BodyCapabilities(
            sensors=self.sensors,
            actions=frozenset(action_ids),
            limits=self.limits,
            revision=self.revision + 1,
            action_catalog=tuple(current[key] for key in sorted(current)),
            input_catalog=self.input_catalog,
        )

    def unregister_action(self, capability_id: str) -> BodyCapabilities:
        """返回移除后的新快照；不存在的能力不制造新的 revision。"""
        current = {
            item.capability_id: item
            for item in self.list_actions()
            if item.capability_id != capability_id
        }
        action_ids = set(self.actions)
        existed = capability_id in action_ids or len(current) != len(
            self.list_actions()
        )
        if not existed:
            return self
        action_ids.discard(capability_id)
        return BodyCapabilities(
            sensors=self.sensors,
            actions=frozenset(action_ids),
            limits=self.limits,
            revision=self.revision + 1,
            action_catalog=tuple(current[key] for key in sorted(current)),
            input_catalog=self.input_catalog,
        )

    def register_input(self, descriptor: BodyCapabilityDescriptor) -> BodyCapabilities:
        """返回注册后的输入目录快照；输入同样由具体 Adapter 声明。"""
        if not descriptor.capability_id.strip():
            raise ValueError("body input ID must not be blank")
        current = {item.capability_id: item for item in self.list_inputs()}
        sensor_ids = set(self.sensors) | set(current)
        if current.get(descriptor.capability_id) == descriptor:
            return self
        current[descriptor.capability_id] = descriptor
        sensor_ids.add(descriptor.capability_id)
        return BodyCapabilities(
            sensors=frozenset(sensor_ids),
            actions=self.actions,
            limits=self.limits,
            revision=self.revision + 1,
            action_catalog=self.action_catalog,
            input_catalog=tuple(current[key] for key in sorted(current)),
        )

    def unregister_input(self, capability_id: str) -> BodyCapabilities:
        """返回移除后的输入目录快照；不存在的输入不制造新的 revision。"""
        current = {
            item.capability_id: item
            for item in self.list_inputs()
            if item.capability_id != capability_id
        }
        sensor_ids = set(self.sensors)
        existed = capability_id in sensor_ids or len(current) != len(self.list_inputs())
        if not existed:
            return self
        sensor_ids.discard(capability_id)
        return BodyCapabilities(
            sensors=frozenset(sensor_ids),
            actions=self.actions,
            limits=self.limits,
            revision=self.revision + 1,
            action_catalog=self.action_catalog,
            input_catalog=tuple(current[key] for key in sorted(current)),
        )

    def supports_sensor(self, sensor: str) -> bool:
        registered = self.sensors or frozenset(
            item.capability_id for item in self.input_catalog
        )
        return "*" in registered or sensor in registered

    def supports_action(self, action: str) -> bool:
        registered = self.actions or frozenset(
            item.capability_id for item in self.action_catalog
        )
        if "*" in registered or action in registered:
            return True
        aliases = {
            "speech.say": ("body.speak", "speak"),
            "speak": ("body.speak", "speech.say"),
            "body.speak": ("speak", "speech.say"),
            "move_to_anchor": ("body.move_to_anchor", "move.to"),
            "move.to": ("move_to_anchor", "body.move_to_anchor"),
            "move.forward": ("walking", "walk"),
            "move.turn": ("turn",),
            "system.emergency_stop": ("body.emergency_stop", "emergency_stop"),
            "emergency_stop": ("body.emergency_stop", "system.emergency_stop"),
        }
        alias = aliases.get(action, ())
        if any(candidate in registered for candidate in alias) or "*" in registered:
            return True
        return action.startswith("expression.") and (
            "body.expression" in registered or "expression" in registered
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "sensors": sorted(self.sensors),
                "actions": sorted(self.actions),
                "limits": dict(self.limits),
                "revision": self.revision,
                "action_catalog": [item.to_dict() for item in self.list_actions()],
                "input_catalog": [item.to_dict() for item in self.list_inputs()],
            },
        )


__all__ = ("BodyCapabilities", "BodyCapabilityDescriptor")
