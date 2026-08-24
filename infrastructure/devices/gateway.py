"""In-process adapter between typed external bodies and authenticated LAN devices."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Deque, Dict, List

from elfie.body.command_execution import utc_now
from elfie.body.contracts import (
    BodyCommand,
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
)
from infrastructure.devices.body_transport import (
    ExternalEventHandler,
    ExternalTransport,
)

ReceiptHandler = Callable[[CommandReceipt], None]
DEFAULT_COMMAND_CAPACITY_PER_DEVICE = 256
diagnostic_logger = logging.getLogger("elfienest.diagnostics.device_gateway")


class CommandEnqueueResult(str, Enum):
    ACCEPTED = "accepted"
    DISCONNECTED = "disconnected"
    FULL = "full"


class DeviceCommandQueueFullError(RuntimeError):
    """The connected device has not drained previously accepted commands."""


class DeviceGateway:
    """Mutable connection registry; mutation represents current LAN socket state."""

    def __init__(
        self,
        *,
        command_capacity_per_device: int = DEFAULT_COMMAND_CAPACITY_PER_DEVICE,
    ) -> None:
        if command_capacity_per_device <= 0:
            raise ValueError("command_capacity_per_device must be positive")
        self._active_devices: set[str] = set()
        self._commands: Dict[str, Deque[BodyCommand]] = {}
        self._sensor_handlers: Dict[str, ExternalEventHandler] = {}
        self._receipt_handlers: Dict[str, ReceiptHandler] = {}
        self._command_capacity_per_device = command_capacity_per_device
        self._rejected_command_count = 0
        self._lock = Lock()

    def connect_device(self, device_id: str) -> None:
        """Mark an authenticated device socket as able to receive commands."""
        with self._lock:
            self._active_devices.add(device_id)
            self._commands.setdefault(device_id, deque())

    def disconnect_device(self, device_id: str) -> None:
        """Stop dispatching actions to a disconnected device socket."""
        with self._lock:
            self._active_devices.discard(device_id)

    def attach_sensor_handler(
        self, device_id: str, handler: ExternalEventHandler
    ) -> None:
        """Associate one external body sensor consumer with a device identity."""
        with self._lock:
            self._sensor_handlers[device_id] = handler

    def detach_sensor_handler(self, device_id: str) -> None:
        """Remove the body sensor consumer when its transport disconnects."""
        with self._lock:
            self._sensor_handlers.pop(device_id, None)

    def attach_receipt_handler(self, device_id: str, handler: ReceiptHandler) -> None:
        """Associate a receipt consumer for later orchestration integration."""
        with self._lock:
            self._receipt_handlers[device_id] = handler

    def detach_receipt_handler(self, device_id: str) -> None:
        """Remove a receipt consumer before its owning session is released."""
        with self._lock:
            self._receipt_handlers.pop(device_id, None)

    def deliver_sensor_event(self, device_id: str, event: BodySensorEvent) -> bool:
        """Deliver a validated device event only to its registered body transport."""
        with self._lock:
            handler = self._sensor_handlers.get(device_id)
        if handler is None:
            return False
        handler(event)
        return True

    def deliver_receipt(self, device_id: str, receipt: CommandReceipt) -> bool:
        """Deliver a validated asynchronous action receipt to its session owner."""
        with self._lock:
            handler = self._receipt_handlers.get(device_id)
        if handler is None:
            return False
        handler(receipt)
        return True

    def enqueue_command(
        self, device_id: str, command: BodyCommand
    ) -> CommandEnqueueResult:
        """Queue an action for a currently connected device's next protocol poll."""
        report_count = 0
        with self._lock:
            if device_id not in self._active_devices:
                return CommandEnqueueResult.DISCONNECTED
            queued = self._commands.setdefault(device_id, deque())
            if len(queued) >= self._command_capacity_per_device:
                self._rejected_command_count += 1
                count = self._rejected_command_count
                if count & (count - 1) == 0:
                    report_count = count
            else:
                queued.append(command)
                return CommandEnqueueResult.ACCEPTED
        if report_count:
            diagnostic_logger.warning(
                "Device command queue rejected new work at capacity",
                extra={
                    "diagnostic_event": "bounded_queue_backpressure",
                    "component": "device_commands",
                    "capacity": self._command_capacity_per_device,
                    "rejected_count": report_count,
                },
            )
        return CommandEnqueueResult.FULL

    def drain_commands(self, device_id: str) -> List[BodyCommand]:
        """Return each queued action once, in the order issued by Core."""
        with self._lock:
            queued = self._commands.setdefault(device_id, deque())
            commands = list(queued)
            queued.clear()
        return commands


class DeviceGatewayTransport(ExternalTransport):
    """ExternalTransport adapter that speaks through an authenticated device gateway."""

    def __init__(self, gateway: DeviceGateway, device_id: str) -> None:
        self.transport_id = f"device-gateway:{device_id}"
        self._gateway = gateway
        self._device_id = device_id
        self._connected = False

    def connect(self, event_handler: ExternalEventHandler) -> None:
        """Attach the owning ExternalBody to inbound device sensor events."""
        self._gateway.attach_sensor_handler(self._device_id, event_handler)
        self._connected = True

    def disconnect(self) -> None:
        """Release only this transport's body listener."""
        self._gateway.detach_sensor_handler(self._device_id)
        self._connected = False

    def send_command(self, command: BodyCommand) -> CommandReceipt:
        """Queue a typed command and acknowledge gateway acceptance, or fail closed."""
        if not self._connected:
            raise ConnectionError("设备网关未连接，无法投递动作")
        result = self._gateway.enqueue_command(self._device_id, command)
        if result is CommandEnqueueResult.DISCONNECTED:
            raise ConnectionError("设备网关未连接，无法投递动作")
        if result is CommandEnqueueResult.FULL:
            raise DeviceCommandQueueFullError("设备命令队列已满，请稍后重试")
        return CommandReceipt.for_status(
            command,
            CommandStatus.ACCEPTED,
            occurred_at=_current_time(),
        )


def _current_time() -> datetime:
    """Keep command acceptance timestamps consistent with BodyPort command validation."""
    return utc_now()
