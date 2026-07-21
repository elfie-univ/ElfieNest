"""毛绒玩具、机器人和母星代理共用的 External BodyPort。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Mapping, Optional, Tuple, overload

from elfie.body.capabilities import BodyCapabilities
from elfie.body.command_execution import (
    WireValue,
    lifecycle_receipts,
    parse_wire_command,
    rejected,
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
from elfie.body.contracts import (
    CommandStatus as ReceiptStatus,
)
from elfie.body.external.actuators import ExternalActuators
from elfie.body.external.sensors import ExternalSensors
from elfie.body.external.transport import ExternalTransport
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
from elfie.message_types import ErrorInfo


class ExternalBody:
    """把外部插件提供的传输实现适配为统一 BodyPort。"""

    def __init__(
        self,
        body_id: str,
        display_name: str,
        capabilities: BodyCapabilities,
        transport: ExternalTransport,
    ) -> None:
        self.body_id = body_id
        self.display_name = display_name
        self.capabilities = capabilities
        self.transport = transport
        self.sensors = ExternalSensors(capabilities)
        self.actuators = ExternalActuators(capabilities, transport)
        self.connected = False
        self._last_typed_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        if self.connected:
            return
        self.transport.connect(self.sensors.receive)
        self.actuators.connected = True
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.transport.disconnect()
        self.actuators.connected = False
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.EXTERNAL,
            display_name=self.display_name,
            capabilities=self.capabilities,
        )

    def read_events(self) -> List[BodyEvent]:
        if not self.connected:
            return []
        return self.sensors.read_events()

    def read_sensor_events(self) -> List[BodySensorEvent]:
        if not self.connected:
            return []
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
            metadata={
                "transport_id": self.transport.transport_id,
                "transport": dict(self.transport.snapshot()),
            },
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
        try:
            terminal = self.transport.send_command(command)
        except (ConnectionError, OSError, RuntimeError) as error:
            failed = CommandReceipt.for_status(
                command,
                ReceiptStatus.FAILED,
                occurred_at=now,
                error=ErrorInfo(
                    code="transport_failure",
                    message=str(error) or "external transport failed",
                    retryable=True,
                ),
            )
            receipts = lifecycle_receipts(command, occurred_at=now, terminal=failed)
            self._last_typed_receipt = receipts[-1]
            return receipts
        if not isinstance(terminal, CommandReceipt):
            receipt = rejected(
                command,
                "bad_transport_receipt",
                "external transport returned an invalid receipt",
                now,
            )
            self._last_typed_receipt = receipt
            return (receipt,)
        if (
            terminal.command_id != command.command_id
            or terminal.turn_id != command.turn_id
            or terminal.intent_id != command.intent_id
        ):
            receipt = rejected(
                command,
                "receipt_correlation_mismatch",
                "external receipt does not correlate to the command",
                now,
            )
            self._last_typed_receipt = receipt
            return (receipt,)
        receipts = lifecycle_receipts(command, occurred_at=now, terminal=terminal)
        self._last_typed_receipt = receipts[-1]
        return receipts
