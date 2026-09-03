from __future__ import annotations

from datetime import datetime, timedelta, timezone

import elfie.body as body_api
import elfie.body.port as body_port_module
import elfie.body.types as body_types
from elfie.body import (
    BodyCapabilities,
    BodyCapabilityDescriptor,
    BodyCommand,
    BodyDescriptor,
    BodyId,
    BodyMode,
    BodyPort,
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
    CommandStatus,
    HeadlessBody,
    MotionCommand,
)
from elfie.message_types import CommandId, IntentId, TurnId
from elfie.nervous_system import NervousSystem

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def test_headless_body_implements_body_port() -> None:
    body = HeadlessBody()

    assert isinstance(body, BodyPort)
    assert body.describe().mode.value == "headless"
    assert body.describe().capabilities.supports_sensor("vision") is True
    assert body.describe().capabilities.supports_action("tail.wag") is True


def test_body_public_api_exposes_only_typed_boundary_contracts() -> None:
    legacy_symbols = (
        "LegacyBodyPort",
        "LegacyBodyCommand",
        "LegacyBodyEvent",
        "LegacyCommandResult",
        "LegacyCommandStatus",
        "BodyEvent",
        "CommandResult",
        "BodyState",
    )

    assert all(not hasattr(body_api, name) for name in legacy_symbols)
    assert all(not hasattr(body_types, name) for name in legacy_symbols)
    assert not hasattr(body_port_module, "LegacyBodyPort")
    assert not hasattr(NervousSystem, "receive")
    assert not hasattr(NervousSystem, "receive_legacy")


class MinimalBody:
    """证明 BodyPort 不要求调用方接触身体内部 sensors/actuators。"""

    body_id = "minimal"
    capabilities = BodyCapabilities()

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.HEADLESS,
            display_name="Minimal Body",
            capabilities=self.capabilities,
        )

    def list_actions(self, *, model_visible: bool = False):
        return self.capabilities.list_actions(model_visible=model_visible)

    def list_inputs(self, *, model_visible: bool = False):
        return self.capabilities.list_inputs(model_visible=model_visible)

    def register_action(self, descriptor: BodyCapabilityDescriptor) -> BodyCapabilities:
        self.capabilities = self.capabilities.register_action(descriptor)
        return self.capabilities

    def unregister_action(self, capability_id: str) -> BodyCapabilities:
        self.capabilities = self.capabilities.unregister_action(capability_id)
        return self.capabilities

    def register_input(self, descriptor: BodyCapabilityDescriptor) -> BodyCapabilities:
        self.capabilities = self.capabilities.register_input(descriptor)
        return self.capabilities

    def unregister_input(self, capability_id: str) -> BodyCapabilities:
        self.capabilities = self.capabilities.unregister_input(capability_id)
        return self.capabilities

    def read_sensor_events(self) -> list[BodySensorEvent]:
        return []

    def execute(
        self,
        command: BodyCommand,
        *,
        now: datetime | None = None,
    ) -> tuple[CommandReceipt, ...]:
        return (CommandReceipt.completed(command, occurred_at=now or NOW),)

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot:
        return BodySnapshot(
            body_id=BodyId(self.body_id),
            captured_at=now or NOW,
            connected=True,
            capability_revision=1,
        )


def test_body_port_exposes_one_receive_and_one_control_entry() -> None:
    body = MinimalBody()
    command = MotionCommand(
        command_type="motion",
        command_id=CommandId("command-1"),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId("minimal"),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        kind="gesture.wave",
    )

    assert isinstance(body, BodyPort)
    assert body.read_sensor_events() == []
    assert body.execute(command, now=NOW)[0].status is CommandStatus.COMPLETED
    assert not hasattr(body, "sensors")
    assert not hasattr(body, "actuators")


def test_body_capability_catalog_is_registered_and_mutated_at_body_boundary() -> None:
    body = HeadlessBody(body_id="body-1", capabilities=BodyCapabilities())
    action = BodyCapabilityDescriptor(
        capability_id="move.forward",
        description="向前移动",
        argument_schema={"type": "object"},
    )
    sensor = BodyCapabilityDescriptor(capability_id="proprioception")

    assert body.list_actions() == ()
    assert body.list_inputs() == ()

    action_snapshot = body.register_action(action)
    body.register_input(sensor)

    assert body.capabilities.action_catalog == (action,)
    assert action_snapshot.action_catalog == (action,)
    assert body.list_actions() == (action,)
    assert body.capabilities.supports_action("move.forward")
    assert body.list_inputs() == (sensor,)
    assert body.capabilities.supports_sensor("proprioception")
    assert body.capabilities.revision == 3

    body.unregister_action("move.forward")
    body.unregister_input("proprioception")
    assert body.list_actions() == ()
    assert body.list_inputs() == ()
