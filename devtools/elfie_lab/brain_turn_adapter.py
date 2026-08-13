"""Elfie Lab adapter for explicit Communication and Embodied Brain turns."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from time import monotonic

from devtools.elfie_lab.schemas import StimulusBundle
from elfie import Elfie
from elfie.body import (
    BodyId,
    BodySensorEvent,
    EnvironmentSample,
    TactileImpact,
    UtteranceFinal,
    VisionChange,
    VisionSample,
)
from elfie.brain.journal import BrainJournalKind
from elfie.brain.reasoning.decision_types import TurnDecision
from elfie.brain.reasoning.execution_types import ExecutionReceipt
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
)
from elfie.brain.reasoning.run import ReasoningRunResult
from elfie.brain.reasoning.tool_port import ToolKey, ToolRequest, ToolResult
from elfie.brain.reasoning.turn_outcome import TurnOutcome
from elfie.communication import (
    CommunicationEnvelope,
    ContentPart,
    DeliveryReceipt,
    DeliveryStatus,
    FilePart,
    ImagePart,
    MessageDirection,
    TextPart,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ErrorInfo,
    EventId,
    MediaRef,
    MessageMeta,
    TraceId,
)

_TURN_WAIT_TIMEOUT_SECONDS = 180.0


class RuntimeSelectionMissingError(RuntimeError):
    """The Lab attempted a turn before selecting its requested runtime."""


class SelectedLabRuntime:
    """Stable runtime port whose per-turn delegate is selected by the Lab."""

    def __init__(self) -> None:
        self._selected: ModelPort | None = None
        self._lock = Lock()

    def select(self, runtime: ModelPort) -> None:
        with self._lock:
            self._selected = runtime

    def capabilities(self) -> ModelGenerationCapabilities:
        return self._current().capabilities()

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        return self._current().generate(request)

    def abandon(self, request: ModelGenerationRequest) -> None:
        self._current().abandon(request)

    def current(self) -> ModelPort:
        return self._current()

    def _current(self) -> ModelPort:
        with self._lock:
            selected = self._selected
        if selected is None:
            raise RuntimeSelectionMissingError("Lab runtime is not selected")
        return selected


class SelectedLabToolPort:
    """Forward semantic tools from the currently selected Lab runtime."""

    def __init__(self, runtime: SelectedLabRuntime) -> None:
        self._runtime = runtime

    def available_tool_keys(self) -> tuple[ToolKey, ...]:
        tool_port = getattr(self._runtime.current(), "tool_port", None)
        if tool_port is None:
            return ()
        return tuple(tool_port.available_tool_keys())

    def execute(self, request: ToolRequest) -> ToolResult:
        tool_port = getattr(self._runtime.current(), "tool_port", None)
        if tool_port is None:
            message = "当前 Lab Runtime 未提供语义工具。"
            return ToolResult(
                tool_key=request.tool_key,
                ok=False,
                content=message,
                error=ErrorInfo(code="tool_unavailable", message=message),
            )
        return tool_port.execute(request)


class LabCommunicationChannel:
    """Connected in-memory boundary that makes Lab replies observable."""

    channel_id = "elfie-lab"

    def __init__(self) -> None:
        self._connected = False
        self.sent: list[CommunicationEnvelope] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        self.sent.append(envelope)
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


class BrainTurnAdapter:
    """Submit one explicit input lane, then wait on the production Brain lifecycle."""

    def __init__(self, elfie: Elfie) -> None:
        self._elfie = elfie
        self._runtime = SelectedLabRuntime()
        self._tools = SelectedLabToolPort(self._runtime)
        self.channel = LabCommunicationChannel()
        self._elfie.register_communication_channel(self.channel, connect=True)
        self._elfie.configure_cognition(self._runtime, tool_port=self._tools)
        self._elfie.start()

    def run(
        self,
        stimulus: StimulusBundle,
        event_id: str,
        runtime: ModelPort,
    ) -> tuple[
        TurnOutcome,
        TurnDecision | None,
        tuple[ExecutionReceipt, ...],
        ReasoningRunResult | None,
    ]:
        self._runtime.select(runtime)
        previous_count = len(self._elfie.turn_outcomes())
        if stimulus.source_domain == "communication":
            envelope = self._communication_envelope(stimulus, event_id)
            submitted_event_ids = (envelope.meta.event_id,)
            self._elfie.receive_communication_envelope(envelope)
        else:
            events = self._events(stimulus, event_id)
            submitted_event_ids = tuple(event.event_id for event in events)
            self._elfie.pump_body_events(events)
        self._elfie.advance_clock(5.0)
        outcome = self._wait_for_submitted_events(
            submitted_event_ids, previous_count=previous_count
        )
        if self._elfie.turn_decision(outcome.turn_id) is not None:
            self._elfie.wait_for_output(
                outcome.turn_id,
                timeout=_TURN_WAIT_TIMEOUT_SECONDS,
            )
        return (
            outcome,
            self._elfie.turn_decision(outcome.turn_id),
            self._elfie.execution_receipts(outcome.turn_id),
            self._elfie.turn_reasoning(outcome.turn_id),
        )

    def _wait_for_submitted_events(
        self,
        event_ids: tuple[EventId, ...],
        *,
        previous_count: int,
    ) -> TurnOutcome:
        """Skip older internal housekeeping Turns and return this input's Turn."""
        deadline = monotonic() + _TURN_WAIT_TIMEOUT_SECONDS
        outcome_index = previous_count
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Lab input did not reach a Turn: {event_ids}")
            self._elfie.wait_for_outcome_count(
                outcome_index + 1,
                timeout=remaining,
            )
            outcomes = self._elfie.turn_outcomes()
            outcome = outcomes[outcome_index]
            if self._turn_contains_any_event(outcome, event_ids):
                return outcome
            outcome_index += 1
            # A prior receipt/reconciliation Turn can legitimately be ahead of
            # the new input after restart. Give the owner loop a fresh pulse so
            # the still-pending input forms its own independent Turn.
            self._elfie.advance_clock(0.001)

    def _turn_contains_any_event(
        self,
        outcome: TurnOutcome,
        event_ids: tuple[EventId, ...],
    ) -> bool:
        submitted = frozenset(event_ids)
        return any(
            entry.kind is BrainJournalKind.RUN_STARTED
            and entry.turn_id == outcome.turn_id
            and not submitted.isdisjoint(entry.cause_event_ids)
            for entry in self._elfie.brain_journal()
        )

    def close(self) -> None:
        self._elfie.stop()
        self._elfie.join()

    def _communication_envelope(
        self, stimulus: StimulusBundle, event_id: str
    ) -> CommunicationEnvelope:
        now = self._elfie.cognitive_datetime
        owner = ActorRef(actor_id=ActorId("elfie-lab-owner"), source_kind="owner")
        parts: list[ContentPart] = []
        if stimulus.message.strip():
            parts.append(TextPart(text=stimulus.message.strip()))
        for attachment in stimulus.message_attachments:
            filename = str(attachment["filename"])
            media = MediaRef.model_validate(
                {key: value for key, value in attachment.items() if key != "filename"}
            )
            if media.mime_type.startswith("image/"):
                parts.append(ImagePart(media=media, caption=filename))
            else:
                parts.append(FilePart(media=media, filename=filename))
        return CommunicationEnvelope(
            meta=MessageMeta(
                event_id=EventId(event_id),
                elfie_id=self._elfie.identity.elfie_id,
                source=owner,
                occurred_at=now,
                received_at=now,
                trace_id=TraceId(f"trace-{event_id}"),
            ),
            account_id="elfie-lab-account",
            channel_id=self.channel.channel_id,
            conversation_id="developer-conversation",
            sender=owner,
            recipients=(
                ActorRef(
                    actor_id=ActorId(self._elfie.identity.elfie_id),
                    source_kind="elfie",
                ),
            ),
            direction=MessageDirection.INBOUND,
            external_message_id=event_id,
            dedupe_key=event_id,
            parts=tuple(parts),
        )

    def _events(
        self,
        stimulus: StimulusBundle,
        event_id: str,
    ) -> tuple[BodySensorEvent, ...]:
        now = self._elfie.cognitive_datetime
        source = ActorRef(actor_id=ActorId("elfie-lab"), source_kind="developer_tool")
        body_id = BodyId(
            self._elfie.current_body.body_id
            if self._elfie.current_body is not None
            else "elfie-lab-body"
        )
        events: list[BodySensorEvent] = []
        message = stimulus.message.strip()
        if message:
            events.append(
                self._event(
                    EventId(event_id),
                    body_id,
                    source,
                    now,
                    UtteranceFinal(kind="utterance_final", text=message),
                )
            )
        if stimulus.vision_media is not None:
            media = MediaRef.model_validate(stimulus.vision_media)
            events.append(
                self._event(
                    EventId(f"{event_id}:vision"),
                    body_id,
                    source,
                    now,
                    VisionSample(kind="vision_sample", media=media),
                )
            )
            if not message:
                events.append(
                    self._event(
                        EventId(f"{event_id}:vision-change"),
                        body_id,
                        source,
                        now,
                        VisionChange(
                            kind="vision_change",
                            description="开发者提交了一帧新的视觉输入",
                            media=media,
                        ),
                    )
                )
        events.append(
            self._event(
                EventId(f"{event_id}:environment"),
                body_id,
                source,
                now,
                EnvironmentSample(
                    kind="environment_sample",
                    temperature_celsius=stimulus.temperature,
                ),
            )
        )
        if stimulus.impact_force > 0 or stimulus.gentle_stroke > 0:
            events.append(
                self._event(
                    EventId(f"{event_id}:tactile"),
                    body_id,
                    source,
                    now,
                    TactileImpact(
                        kind="tactile_impact",
                        location=stimulus.impact_direction or "body",
                        force_newtons=max(
                            stimulus.impact_force, stimulus.gentle_stroke
                        ),
                    ),
                )
            )
        return tuple(events)

    @staticmethod
    def _event(
        event_id: EventId,
        body_id: BodyId,
        source: ActorRef,
        now: datetime,
        payload: (
            EnvironmentSample
            | TactileImpact
            | UtteranceFinal
            | VisionChange
            | VisionSample
        ),
    ) -> BodySensorEvent:
        return BodySensorEvent(
            event_id=event_id,
            body_id=body_id,
            source=source,
            occurred_at=now,
            received_at=now,
            payload=payload,
        )


__all__ = ("BrainTurnAdapter", "SelectedLabRuntime", "SelectedLabToolPort")
