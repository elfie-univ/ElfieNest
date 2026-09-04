from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Literal, Optional, Tuple, cast

from elfie.body.contracts import (
    ActionOutcomePayload,
    BodyCommand,
    BodyId,
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
)
from elfie.body.port import BodyPort
from elfie.brain.workspace.contracts import IngestReceipt
from elfie.brain.workspace.ports import PerceptionSink
from elfie.message_types import ActorId, ActorRef, ElfieId, EventId
from elfie.nervous_system.actuators import (
    MutterActuator,
    SpeechActuator,
)
from elfie.nervous_system.perception_bridge import BodyPerceptionBridge
from elfie.nervous_system.perception_normalizer import BodyPerceptionNormalizer
from elfie.nervous_system.signal_filter import SensoryDamSignalFilter


class PerceptionBridgeNotConfiguredError(RuntimeError):
    """Raised when typed Body input arrives before sink injection."""


class NervousSystem:
    """统一大脑与身体之间的感知、过滤和类型化命令传递入口。"""

    def __init__(
        self,
        *,
        perception_sink: Optional[PerceptionSink] = None,
        elfie_id: Optional[ElfieId] = None,
        body_port: Optional[BodyPort] = None,
        body_generation: int | None = None,
        logical_clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.speech_actuator = SpeechActuator()
        self.mutter_actuator = MutterActuator()

        self.signal_filter = SensoryDamSignalFilter()
        self._perception_bridge: Optional[BodyPerceptionBridge] = None
        self._perception_notifier: Optional[Callable[[], None]] = None
        # External Bodies report wall-clock occurrence times, while Brain uses
        # Elfie's own simulation/cognitive clock.  Keep the source time in
        # ``received_at`` and stamp the re-entering fact on the Brain clock.
        self._logical_clock = logical_clock
        if perception_sink is not None and elfie_id is not None:
            self._perception_bridge = BodyPerceptionBridge(
                sink=perception_sink,
                elfie_id=elfie_id,
                normalizer=BodyPerceptionNormalizer(elfie_id, self.signal_filter),
                body_port=body_port,
                body_generation=body_generation,
            )
        elif perception_sink is not None or elfie_id is not None:
            raise PerceptionBridgeNotConfiguredError(
                "perception_sink and elfie_id must be injected together"
            )

    @property
    def pending_count(self) -> int:
        return self._require_perception_bridge().pending_count

    @property
    def perception_configured(self) -> bool:
        """Whether terminal Body outcomes can re-enter the Brain boundary."""
        return self._perception_bridge is not None

    @property
    def filtered_count(self) -> int:
        return self._require_perception_bridge().filtered_count

    @property
    def dropped_pending_count(self) -> int:
        return self._require_perception_bridge().dropped_pending_count

    @property
    def urgent_revision(self) -> int:
        return self._require_perception_bridge().urgent_revision

    @property
    def last_reflex_command(self) -> Optional[EmergencyStopCommand]:
        return self._require_perception_bridge().last_reflex_command

    def receive_body_events(
        self,
        events: Iterable[BodySensorEvent],
    ) -> Tuple[IngestReceipt, ...]:
        """Publish a typed Body batch without flattening event identity."""
        return self._require_perception_bridge().receive(events)

    def receive_body_event(
        self,
        event: BodySensorEvent,
    ) -> Tuple[IngestReceipt, ...]:
        """Process one Body event through reflex, filter, and Brain publish."""
        return self._require_perception_bridge().receive_body_event(event)

    def bind_body_port(
        self,
        body_port: Optional[BodyPort],
        *,
        body_generation: int | None = None,
    ) -> None:
        """Keep the immediate reflex target aligned with the active Body."""
        self._require_perception_bridge().bind_body_port(
            body_port,
            body_generation=body_generation,
        )

    def bind_perception_notifier(
        self,
        notifier: Optional[Callable[[], None]],
    ) -> None:
        """Wake the generic Brain perception loop after direct Body input."""
        self._perception_notifier = notifier

    def retry_pending(self) -> Tuple[IngestReceipt, ...]:
        """Retry reliable writes retained after Workspace backpressure."""
        return self._require_perception_bridge().retry_pending()

    def close_perception(self) -> None:
        """Close the Body-to-Brain input boundary."""
        self._require_perception_bridge().close()

    def _require_perception_bridge(self) -> BodyPerceptionBridge:
        bridge = self._perception_bridge
        if bridge is None:
            raise PerceptionBridgeNotConfiguredError(
                "typed perception bridge is not configured"
            )
        return bridge

    def execute_body_command(
        self,
        body: BodyPort,
        command: BodyCommand,
        *,
        now: datetime,
    ) -> Tuple[CommandReceipt, ...]:
        """Pass an already typed physical intent to the current Body boundary."""
        receipts = body.execute(command, now=now)
        terminal = next(
            (
                receipt
                for receipt in reversed(receipts)
                if receipt.status not in {CommandStatus.ACCEPTED, CommandStatus.STARTED}
            ),
            None,
        )
        if terminal is not None and self._perception_bridge is not None:
            self.receive_body_event(
                BodySensorEvent(
                    event_id=terminal.receipt_id,
                    cause_id=terminal.cause_id or EventId(str(command.command_id)),
                    body_id=BodyId(str(body.body_id)),
                    body_generation=terminal.body_generation,
                    source=ActorRef(
                        actor_id=ActorId(str(body.body_id)),
                        source_kind="body",
                    ),
                    occurred_at=(
                        self._logical_clock()
                        if self._logical_clock is not None
                        else terminal.occurred_at
                    ),
                    received_at=terminal.occurred_at,
                    payload=ActionOutcomePayload(
                        kind="action_outcome",
                        command_id=str(terminal.command_id),
                        intent_id=str(terminal.intent_id),
                        status=cast(
                            Literal[
                                "completed",
                                "rejected",
                                "failed",
                                "interrupted",
                                "timed_out",
                            ],
                            terminal.status.value,
                        ),
                        reason=(
                            terminal.error.message
                            if terminal.error is not None
                            else None
                        ),
                    ),
                )
            )
            notifier = self._perception_notifier
            if notifier is not None:
                notifier()
        return receipts

    def filter_signals(self, raw_sensor_data: Dict[str, Any]) -> bool:
        """过滤重复或无价值的感知信号。"""
        return self.signal_filter.filter_noise(raw_sensor_data)

    def speak(self, text: str) -> str:
        """把说话意图交给文本发言执行器。"""
        return self.speech_actuator.speak(text)

    def mutter(self, status: str) -> str:
        """把内部状态转换为精灵的碎碎念。"""
        return self.mutter_actuator.mutter(status)
