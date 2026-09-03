"""毛绒玩具、机器人和母星代理共用的 External BodyPort。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Mapping, Tuple

from elfie.body.capabilities import BodyCapabilities, BodyCapabilityDescriptor
from elfie.body.command_execution import (
    WireValue,
    lifecycle_receipts,
    parse_wire_command,
    rejected,
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
from elfie.body.contracts import (
    CommandStatus as ReceiptStatus,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyMode,
)
from elfie.message_types import ErrorInfo
from infrastructure.devices.body_sensors import ExternalSensors
from infrastructure.devices.body_transport import ExternalTransport


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
        self.connected = False
        self._last_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        if self.connected:
            return
        self.transport.connect(self.sensors.receive)
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.transport.disconnect()
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=BodyId(self.body_id),
            mode=BodyMode.EXTERNAL,
            display_name=self.display_name,
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

    def read_sensor_events(self) -> List[BodySensorEvent]:
        if not self.connected:
            return []
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
            self._last_receipt = receipts[-1]
            return receipts
        if not isinstance(terminal, CommandReceipt):
            receipt = rejected(
                command,
                "bad_transport_receipt",
                "external transport returned an invalid receipt",
                now,
            )
            self._last_receipt = receipt
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
            self._last_receipt = receipt
            return (receipt,)
        receipts = lifecycle_receipts(command, occurred_at=now, terminal=terminal)
        self._last_receipt = receipts[-1]
        return receipts
