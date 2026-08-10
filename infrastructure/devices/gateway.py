"""In-process adapter between typed external bodies and authenticated LAN devices."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime
from threading import Lock
from typing import Deque, Dict, List

from elfie.body.command_execution import utc_now
from elfie.body.contracts import (
    BodyCommand,
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
)
from elfie.body.external.transport import ExternalEventHandler, ExternalTransport

ReceiptHandler = Callable[[CommandReceipt], None]


class DeviceGateway:
    """Mutable connection registry; mutation represents current LAN socket state."""

    def __init__(self) -> None:
        self._active_devices: set[str] = set()
        self._commands: Dict[str, Deque[BodyCommand]] = {}
        self._sensor_handlers: Dict[str, ExternalEventHandler] = {}
        self._receipt_handlers: Dict[str, ReceiptHandler] = {}
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

    def enqueue_command(self, device_id: str, command: BodyCommand) -> bool:
        """Queue an action for a currently connected device's next protocol poll."""
        with self._lock:
            if device_id not in self._active_devices:
                return False
            self._commands.setdefault(device_id, deque()).append(command)
        return True

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
        if not self._connected or not self._gateway.enqueue_command(
            self._device_id, command
        ):
            raise ConnectionError("设备网关未连接，无法投递动作")
        return CommandReceipt.for_status(
            command,
            CommandStatus.ACCEPTED,
            occurred_at=_current_time(),
        )


def _current_time() -> datetime:
    """Keep command acceptance timestamps consistent with BodyPort command validation."""
    return utc_now()
