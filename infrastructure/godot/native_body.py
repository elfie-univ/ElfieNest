"""Godot 中精灵本体的 BodyPort 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Mapping, Optional, Tuple, cast

from pydantic import JsonValue

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
    CapabilityCommand,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    MotionCommand,
    ObservationCommand,
    SpeechCommand,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyMode,
)
from elfie.message_types import ErrorInfo, EventId
from infrastructure.godot.body_sensors import NativeSensors
from infrastructure.godot.body_transport import GodotTransport, RuntimeIntentPayload

_ACTION_OUTCOME_SCHEMA = cast(
    Mapping[str, JsonValue],
    {
        "type": "object",
        "required": ["kind", "command_id", "intent_id", "status"],
        "properties": {
            "kind": {"const": "action_outcome"},
            "command_id": {"type": "string"},
            "intent_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": [
                    "completed",
                    "rejected",
                    "failed",
                    "interrupted",
                    "timed_out",
                ],
            },
            "reason": {"type": "string"},
        },
    },
)


class NativeBody:
    """连接精灵本体与现有 Godot API，不实现大脑或运动算法。"""

    def __init__(
        self,
        body_id: str,
        transport: GodotTransport,
        capabilities: Optional[BodyCapabilities] = None,
    ):
        self.body_id = body_id
        self.transport = transport
        self.capabilities = capabilities or BodyCapabilities(
            sensors=frozenset({"hearing", "vision", "touch", "proprioception"}),
            actions=frozenset(
                {
                    "move.forward",
                    "move.turn",
                    "speak",
                    "expression",
                    "emergency_stop",
                }
            ),
            action_catalog=(
                BodyCapabilityDescriptor(
                    capability_id="move.forward",
                    description="Move the Elfie forward by a bounded distance.",
                    argument_schema={
                        "type": "object",
                        "required": ["distance"],
                        "properties": {
                            "distance": {
                                "type": "number",
                                "minimum": 0.05,
                                "maximum": 5.0,
                            }
                        },
                        "additionalProperties": False,
                    },
                    return_schema=_ACTION_OUTCOME_SCHEMA,
                    registration_source="godot.native_body",
                ),
                BodyCapabilityDescriptor(
                    capability_id="move.turn",
                    description="Turn the Elfie in place by an angle in degrees.",
                    argument_schema={
                        "type": "object",
                        "required": ["angle_degrees"],
                        "properties": {
                            "angle_degrees": {
                                "type": "number",
                                "minimum": -360.0,
                                "maximum": 360.0,
                            }
                        },
                        "additionalProperties": False,
                    },
                    return_schema=_ACTION_OUTCOME_SCHEMA,
                    registration_source="godot.native_body",
                ),
                BodyCapabilityDescriptor(
                    capability_id="speak",
                    description="Speak text through the current avatar voice.",
                    argument_schema={
                        "type": "object",
                        "required": ["text"],
                        "properties": {"text": {"type": "string", "minLength": 1}},
                        "additionalProperties": False,
                    },
                    return_schema=_ACTION_OUTCOME_SCHEMA,
                    registration_source="godot.native_body",
                ),
                BodyCapabilityDescriptor(
                    capability_id="expression",
                    description="Play a named facial or body expression.",
                    argument_schema={
                        "type": "object",
                        "required": ["kind"],
                        "properties": {
                            "kind": {"type": "string", "minLength": 1},
                            "intensity": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                        },
                        "additionalProperties": False,
                    },
                    return_schema=_ACTION_OUTCOME_SCHEMA,
                    registration_source="godot.native_body",
                ),
                BodyCapabilityDescriptor(
                    capability_id="emergency_stop",
                    description="Stop all currently active avatar commands.",
                    argument_schema={
                        "type": "object",
                        "properties": {"reason": {"type": "string", "minLength": 1}},
                        "additionalProperties": False,
                    },
                    return_schema=_ACTION_OUTCOME_SCHEMA,
                    registration_source="godot.native_body",
                ),
            ),
            input_catalog=tuple(
                BodyCapabilityDescriptor(
                    capability_id=name,
                    description=description,
                    return_schema=cast(Mapping[str, JsonValue], return_schema),
                    registration_source="godot.native_body",
                )
                for name, description, return_schema in (
                    (
                        "hearing",
                        "Receive structured utterances heard by this Elfie.",
                        {
                            "type": "object",
                            "required": ["kind", "text"],
                            "properties": {"kind": {"const": "utterance_final"}},
                        },
                    ),
                    (
                        "vision",
                        "Receive semantic entities visible to this Elfie.",
                        {
                            "type": "object",
                            "required": ["kind", "observation_id", "entities"],
                            "properties": {
                                "kind": {"const": "semantic_visual_scene"},
                                "observation_id": {"type": "string"},
                                "entities": {"type": "array"},
                            },
                        },
                    ),
                    (
                        "touch",
                        "Receive collision and tactile impact events.",
                        {
                            "type": "object",
                            "required": ["kind", "intensity", "direction"],
                            "properties": {
                                "kind": {"const": "tactile_impact"},
                                "intensity": {"type": "number"},
                                "direction": {"type": "string"},
                            },
                        },
                    ),
                    (
                        "proprioception",
                        "Receive posture, zone, pose and active-command state.",
                        {
                            "type": "object",
                            "required": ["kind", "posture", "arrived"],
                            "properties": {
                                "kind": {"const": "proprioception_sample"},
                                "posture": {"type": "string"},
                                "position": {
                                    "type": "array",
                                    "minItems": 3,
                                    "maxItems": 3,
                                },
                                "heading_degrees": {"type": "number"},
                                "velocity": {
                                    "type": "array",
                                    "minItems": 3,
                                    "maxItems": 3,
                                },
                            },
                        },
                    ),
                )
            ),
        )
        self.sensors = NativeSensors(body_id)
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
        self.transport.disconnect(self.sensors.receive)
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=BodyId(self.body_id),
            mode=BodyMode.NATIVE,
            display_name="Native Godot Body",
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

    def ingest_sensor_events(self, events: Iterable[BodySensorEvent]) -> None:
        """Route semantic Nest facts into the same Body input queue as runtime facts."""
        self.sensors.ingest(events)

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
        payload: RuntimeIntentPayload
        if isinstance(command, SpeechCommand):
            payload = {
                "command_id": str(command.command_id),
                "intent_id": str(command.intent_id),
                "actor_id": self.body_id,
                "body_generation": command.body_generation,
                "initiator": "elfie",
                "intent": "speak",
                "text": command.text,
            }
        elif isinstance(command, MotionCommand):
            if command.target:
                payload = {
                    "command_id": str(command.command_id),
                    "intent_id": str(command.intent_id),
                    "actor_id": self.body_id,
                    "body_generation": command.body_generation,
                    "initiator": "elfie",
                    "intent": "move_to_anchor",
                    "anchor_id": command.target,
                }
            else:
                if command.kind == "gesture.wave":
                    payload = {
                        "command_id": str(command.command_id),
                        "intent_id": str(command.intent_id),
                        "actor_id": self.body_id,
                        "body_generation": command.body_generation,
                        "initiator": "elfie",
                        "intent": "emotion_expression",
                        "expression": "wave",
                    }
                else:
                    payload = {
                        "command_id": str(command.command_id),
                        "intent_id": str(command.intent_id),
                        "actor_id": self.body_id,
                        "body_generation": command.body_generation,
                        "initiator": "elfie",
                        "intent": command.kind,
                    }
        elif isinstance(command, ExpressionCommand):
            payload = {
                "command_id": str(command.command_id),
                "intent_id": str(command.intent_id),
                "actor_id": self.body_id,
                "body_generation": command.body_generation,
                "initiator": "elfie",
                "intent": "emotion_expression",
                "expression": command.kind,
            }
        elif isinstance(command, ObservationCommand):
            payload = {
                "command_id": str(command.command_id),
                "intent_id": str(command.intent_id),
                "actor_id": self.body_id,
                "body_generation": command.body_generation,
                "initiator": "elfie",
                "intent": "observe",
                "observation_id": command.observation_id,
                "max_results": command.max_results,
            }
            if not self.transport.request_visual_observation(payload):
                receipt = rejected(
                    command,
                    "visual_observation_unavailable",
                    "semantic visual observation is unavailable",
                    now,
                )
                self._last_receipt = receipt
                return (receipt,)
            receipts = lifecycle_receipts(command, occurred_at=now)
            self._last_receipt = receipts[-1]
            return receipts
        elif isinstance(command, EmergencyStopCommand):
            self.transport.cancel_all(actor_id=self.body_id)
            receipts = (
                CommandReceipt.for_status(
                    command,
                    CommandStatus.ACCEPTED,
                    occurred_at=now,
                ),
                CommandReceipt.completed(command, occurred_at=now),
            )
            self._last_receipt = receipts[-1]
            return receipts
        elif isinstance(command, CapabilityCommand):
            try:
                capability_payload = self._capability_payload(command)
            except ValueError as error:
                receipt = rejected(
                    command,
                    "invalid_capability_arguments",
                    str(error),
                    now,
                )
                self._last_receipt = receipt
                return (receipt,)
            if capability_payload is None:
                receipt = rejected(
                    command,
                    "unsupported_capability",
                    f"Godot adapter has no mapping for {command.capability_id}",
                    now,
                )
                self._last_receipt = receipt
                return (receipt,)
            payload = capability_payload
        timeout_seconds = max((command.deadline - now).total_seconds(), 0.0)
        payload["deadline_seconds"] = timeout_seconds
        result = self.transport.execute_intent(
            payload,
            timeout_seconds=timeout_seconds,
        )
        receipts_list: list[CommandReceipt] = []
        for event in result.events:
            status_value = {
                "intent_accepted": CommandStatus.ACCEPTED,
                "intent_started": CommandStatus.STARTED,
            }.get(event.name.value)
            if status_value is None:
                continue
            receipts_list.append(
                CommandReceipt(
                    receipt_id=EventId(event.message_id),
                    cause_id=(
                        EventId(event.cause_id) if event.cause_id is not None else None
                    ),
                    command_id=command.command_id,
                    turn_id=command.turn_id,
                    intent_id=command.intent_id,
                    body_id=command.body_id,
                    status=status_value,
                    occurred_at=event.occurred_at,
                    capability_revision=command.capability_revision,
                    body_generation=command.body_generation,
                )
            )
        terminal_status = {
            "completed": CommandStatus.COMPLETED,
            "cancelled": CommandStatus.INTERRUPTED,
            "interrupted": CommandStatus.INTERRUPTED,
            "timed_out": CommandStatus.TIMED_OUT,
        }.get(result.terminal_status, CommandStatus.FAILED)
        terminal_error = None
        if terminal_status is not CommandStatus.COMPLETED:
            terminal_error = ErrorInfo(
                code=result.terminal_status,
                message=result.reason or result.terminal_status,
            )
        terminal_event = next(
            (
                event
                for event in reversed(result.events)
                if event.name.value == "intent_terminal"
            ),
            None,
        )
        if terminal_event is None:
            receipts_list.append(
                CommandReceipt.for_status(
                    command,
                    terminal_status,
                    occurred_at=utc_now(),
                    error=terminal_error,
                )
            )
        else:
            receipts_list.append(
                CommandReceipt(
                    receipt_id=EventId(terminal_event.message_id),
                    cause_id=(
                        EventId(terminal_event.cause_id)
                        if terminal_event.cause_id is not None
                        else None
                    ),
                    command_id=command.command_id,
                    turn_id=command.turn_id,
                    intent_id=command.intent_id,
                    body_id=command.body_id,
                    status=terminal_status,
                    occurred_at=terminal_event.occurred_at,
                    capability_revision=command.capability_revision,
                    body_generation=command.body_generation,
                    error=terminal_error,
                )
            )
        final_receipts: tuple[CommandReceipt, ...] = tuple(receipts_list)
        self._last_receipt = final_receipts[-1]
        return final_receipts

    def _capability_payload(
        self, command: CapabilityCommand
    ) -> RuntimeIntentPayload | None:
        """Map a registered public capability to the existing Godot wire verbs."""
        base: RuntimeIntentPayload = {
            "command_id": str(command.command_id),
            "intent_id": str(command.intent_id),
            "actor_id": self.body_id,
            "body_generation": command.body_generation,
            "initiator": "elfie",
        }
        arguments = command.arguments
        if command.capability_id == "move.forward":
            distance = arguments.get("distance")
            if isinstance(distance, bool) or not isinstance(distance, (int, float)):
                raise ValueError("move.forward requires numeric distance")
            return {**base, "intent": "move_forward", "distance": float(distance)}
        if command.capability_id == "move.turn":
            angle = arguments.get("angle_degrees")
            if isinstance(angle, bool) or not isinstance(angle, (int, float)):
                raise ValueError("move.turn requires numeric angle_degrees")
            return {
                **base,
                "intent": "turn",
                "angle_degrees": float(angle),
            }
        if command.capability_id == "speak":
            text = arguments.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("speak requires non-blank text")
            return {**base, "intent": "speak", "text": text}
        if command.capability_id == "expression":
            kind = arguments.get("kind")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("expression requires non-blank kind")
            intensity = arguments.get("intensity")
            payload = cast(
                RuntimeIntentPayload,
                {**base, "intent": "emotion_expression", "expression": kind},
            )
            if isinstance(intensity, (int, float)) and not isinstance(intensity, bool):
                payload["intensity"] = float(intensity)
            return payload
        return None
