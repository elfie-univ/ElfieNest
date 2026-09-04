"""不渲染、不驱动硬件，只接收刺激并记录动作的身体实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Mapping, Optional, Tuple

from elfie.body.capabilities import BodyCapabilities, BodyCapabilityDescriptor
from elfie.body.command_execution import (
    WireValue,
    lifecycle_receipts,
    parse_wire_command,
    utc_now,
    validate_command,
)
from elfie.body.contracts import (
    BodyCommand,
    BodyId,
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
)
from elfie.body.headless.sensors import HeadlessSensors
from elfie.body.types import (
    BodyDescriptor,
    BodyMode,
)


class HeadlessBody:
    """用于调试平台、单元测试和无渲染运行。"""

    def __init__(
        self,
        body_id: str = "headless_default",
        capabilities: Optional[BodyCapabilities] = None,
    ):
        self.body_id = body_id
        self.capabilities = capabilities or BodyCapabilities(
            sensors=frozenset({"*"}),
            actions=frozenset({"*"}),
        )
        self.sensors = HeadlessSensors(source=body_id)
        self.connected = False
        self._last_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=BodyId(self.body_id),
            mode=BodyMode.HEADLESS,
            display_name="Headless Body",
            capabilities=self.capabilities,
        )

    def list_actions(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]:
        return self.capabilities.list_actions(model_visible=model_visible)

    def list_inputs(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]:
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

    def inject_event(self, event: BodySensorEvent) -> None:
        self.sensors.inject_event(event)

    def ingest_sensor_events(self, events: Iterable[BodySensorEvent]) -> None:
        for event in events:
            self.inject_event(event)

    def read_sensor_events(self) -> List[BodySensorEvent]:
        return self.sensors.read_sensor_events()

    def execute(
        self,
        command: BodyCommand,
        *,
        now: datetime | None = None,
    ) -> Tuple[CommandReceipt, ...]:
        return self._execute(command, now=now or utc_now())

    def execute_wire(
        self,
        payload: Mapping[str, WireValue],
        *,
        now: datetime | None = None,
    ) -> Tuple[CommandReceipt, ...]:
        current_time = now or utc_now()
        parsed = parse_wire_command(payload, occurred_at=current_time)
        if isinstance(parsed, CommandReceipt):
            return (parsed,)
        return self._execute(parsed, now=current_time)

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot:
        receipt = self._last_receipt
        return BodySnapshot(
            body_id=BodyId(self.body_id),
            captured_at=now or utc_now(),
            connected=self.connected,
            capability_revision=self.capabilities.revision,
            pending_event_count=self.sensors.pending_count,
            last_command_id=receipt.command_id if receipt else None,
            last_status=receipt.status if receipt else None,
        )

    def _execute(
        self,
        command: BodyCommand,
        *,
        now: datetime,
    ) -> Tuple[CommandReceipt, ...]:
        rejection = validate_command(
            command,
            expected_body_id=self.body_id,
            capabilities=self.capabilities,
            connected=self.connected,
            now=now,
        )
        if rejection is not None:
            self._last_receipt = rejection
            return (rejection,)
        receipts = lifecycle_receipts(command, occurred_at=now)
        self._last_receipt = receipts[-1]
        return receipts
