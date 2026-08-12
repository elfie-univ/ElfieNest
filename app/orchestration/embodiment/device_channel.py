"""Coordinate authenticated body protocol activity with its technical gateway."""

from __future__ import annotations

from typing import Literal

from app.features.bodies import (
    AuthenticateBodyCommand,
    BodiesService,
    BodyPrincipal,
    RecordBodyActivityCommand,
)
from elfie.public import BodyCommand, BodySensorEvent, CommandReceipt

from .ports import BodyDeviceGatewayPort


class BodyProtocolRejected(RuntimeError):
    """A validated protocol model does not belong to its body principal."""


class BodyDeviceChannel:
    def __init__(
        self, *, bodies: BodiesService, gateway: BodyDeviceGatewayPort
    ) -> None:
        self._bodies = bodies
        self._gateway = gateway

    def authenticate(self, bearer_token: str) -> BodyPrincipal:
        return self._bodies.authenticate_body(
            AuthenticateBodyCommand(bearer_token=bearer_token)
        )

    def connect(self, principal: BodyPrincipal) -> None:
        self._gateway.connect_device(principal.body_id)

    def disconnect(self, principal: BodyPrincipal) -> None:
        self._gateway.disconnect_device(principal.body_id)

    def heartbeat(self, principal: BodyPrincipal) -> None:
        self._bodies.record_activity(
            RecordBodyActivityCommand(body_id=principal.body_id, activity="heartbeat")
        )

    def deliver_sensor(self, principal: BodyPrincipal, event: BodySensorEvent) -> bool:
        if str(event.body_id) != principal.body_id:
            raise BodyProtocolRejected("Sensor event body does not match credential")
        delivered = self._gateway.deliver_sensor_event(principal.body_id, event)
        self._record_frame(principal, "sensor_event")
        return delivered

    def deliver_receipt(
        self, principal: BodyPrincipal, receipt: CommandReceipt
    ) -> bool:
        if str(receipt.body_id) != principal.body_id:
            raise BodyProtocolRejected("Receipt body does not match credential")
        delivered = self._gateway.deliver_receipt(principal.body_id, receipt)
        self._record_frame(principal, "receipt")
        return delivered

    def poll_commands(self, principal: BodyPrincipal) -> list[BodyCommand]:
        commands = self._gateway.drain_commands(principal.body_id)
        self._record_frame(principal, "command_poll")
        return commands

    def _record_frame(
        self,
        principal: BodyPrincipal,
        activity: Literal["sensor_event", "receipt", "command_poll"],
    ) -> None:
        self.heartbeat(principal)
        self._bodies.record_activity(
            RecordBodyActivityCommand(
                body_id=principal.body_id,
                activity=activity,
            )
        )


__all__ = ("BodyDeviceChannel", "BodyProtocolRejected")
