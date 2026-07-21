"""不渲染、不驱动硬件，只接收刺激并记录动作的身体实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Mapping, Optional, Tuple, overload

from elfie.body.capabilities import BodyCapabilities
from elfie.body.command_execution import (
    WireValue,
    lifecycle_receipts,
    parse_wire_command,
    utc_now,
    validate_command,
)
from elfie.body.contracts import (
    BodyCommand as TypedBodyCommand,
)
from elfie.body.contracts import (
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
)
from elfie.body.headless.actuators import HeadlessActuators
from elfie.body.headless.sensors import HeadlessSensors
from elfie.body.types import (
    BodyCommand as LegacyBodyCommand,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyState,
)
from elfie.body.types import (
    CommandResult as LegacyCommandResult,
)
from elfie.body.types import (
    CommandStatus as LegacyCommandStatus,
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
        self.actuators = HeadlessActuators(self.capabilities)
        self.connected = False
        self._last_typed_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.HEADLESS,
            display_name="Headless Body",
            capabilities=self.capabilities,
        )

    def inject_sensor_data(
        self,
        sensor_data: Mapping[str, Any],
        *,
        event_id: Optional[str] = None,
    ) -> BodyEvent:
        return self.sensors.inject_sensor_data(sensor_data, event_id=event_id)

    def inject_event(self, event: BodySensorEvent) -> None:
        self.sensors.inject_event(event)

    def read_events(self) -> List[BodyEvent]:
        return self.sensors.read_events()

    def read_sensor_events(self) -> List[BodySensorEvent]:
        return self.sensors.read_sensor_events()

    @overload
    def execute(
        self, command: LegacyBodyCommand, *, now: datetime | None = None
    ) -> LegacyCommandResult: ...

    @overload
    def execute(
        self, command: TypedBodyCommand, *, now: datetime | None = None
    ) -> Tuple[CommandReceipt, ...]: ...

    def execute(
        self,
        command: LegacyBodyCommand | TypedBodyCommand,
        *,
        now: datetime | None = None,
    ) -> LegacyCommandResult | Tuple[CommandReceipt, ...]:
        if isinstance(command, LegacyBodyCommand):
            if not self.connected:
                return LegacyCommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=LegacyCommandStatus.REJECTED,
                    error="HeadlessBody 尚未连接",
                )
            return self.actuators.execute(command)
        return self._execute_typed(command, now=now or utc_now())

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
        return self._execute_typed(parsed, now=current_time)

    def snapshot(self) -> BodyState:
        last_result = self.actuators.last_result
        return BodyState(
            body_id=self.body_id,
            connected=self.connected,
            pending_event_count=self.sensors.pending_count,
            last_action=last_result.action if last_result else "",
        )

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot:
        receipt = self._last_typed_receipt
        return BodySnapshot(
            body_id=self.body_id,
            captured_at=now or utc_now(),
            connected=self.connected,
            capability_revision=self.capabilities.revision,
            pending_event_count=self.sensors.pending_count,
            last_command_id=receipt.command_id if receipt else None,
            last_status=receipt.status if receipt else None,
        )

    def emergency_stop(self) -> LegacyCommandResult:
        result = self.execute(LegacyBodyCommand(action="system.emergency_stop"))
        return result

    @property
    def last_result(self) -> Optional[LegacyCommandResult]:
        return self.actuators.last_result

    def _execute_typed(
        self,
        command: TypedBodyCommand,
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
            self._last_typed_receipt = rejection
            return (rejection,)
        receipts = lifecycle_receipts(command, occurred_at=now)
        self._last_typed_receipt = receipts[-1]
        return receipts
