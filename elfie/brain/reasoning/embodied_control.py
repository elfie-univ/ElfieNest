"""Brain-owned policy for the first-stage embodied input switch."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from enum import Enum, unique
from random import Random
from typing import Optional
from uuid import uuid4

from elfie.brain.reasoning.context_types import EffectiveCapabilities
from elfie.brain.reasoning.coordinator_ports import (
    BrainContextSource,
    TurnDecisionSink,
)
from elfie.brain.reasoning.decision_governance import govern_decision
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    CapabilityIntent,
    DecisionPlan,
)
from elfie.brain.workspace.contracts import (
    IngestDisposition,
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.brain.workspace.types import FrameLifecycleError
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    IntentId,
    MessageMeta,
    PlanId,
    Priority,
    TraceId,
    TurnId,
    UTCDateTime,
)


@unique
class EmbodiedInputMode(str, Enum):
    """Whether embodied input is admitted to Reasoning or absorbed by Mock."""

    MOCK = "mock"
    BRAIN = "brain"


class EmbodiedMockController:
    """Consume routine embodied frames and issue semantic movement through the Router.

    This controller is deliberately owned by the Brain coordinator.  It never
    calls a Body, Gateway, or Godot object directly; every movement is a normal
    governed ``move.to`` decision whose terminal Body feedback re-enters the
    same Workspace lane.
    """

    _MOCK_TICK_CONTENT = "mock_wander_tick"
    _TERMINAL_STATUSES = frozenset(
        {"completed", "rejected", "failed", "interrupted", "timed_out", "cancelled"}
    )

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: EventWorkspace,
        context_source: BrainContextSource,
        plan_sink: TurnDecisionSink,
        rng: Random | None = None,
        move_interval_seconds: tuple[float, float] = (4.0, 10.0),
        action_timeout_seconds: float = 60.0,
    ) -> None:
        minimum, maximum = move_interval_seconds
        if minimum < 0 or maximum < minimum:
            raise ValueError("mock movement interval must be non-negative and ordered")
        if action_timeout_seconds <= 0:
            raise ValueError("mock action timeout must be positive")
        self._elfie_id = elfie_id
        self._workspace = workspace
        self._context_source = context_source
        self._plan_sink = plan_sink
        self._rng = rng or Random()
        self._minimum_interval = minimum
        self._maximum_interval = maximum
        self._action_timeout_seconds = action_timeout_seconds
        self._next_move_at: Optional[float] = None
        self._awaiting_intent: Optional[IntentId] = None
        self._awaiting_deadline: Optional[float] = None
        self._last_target: Optional[str] = None

    def on_clock(self, captured_at: UTCDateTime) -> None:
        """Schedule one synthetic embodied tick during the local 06:00-24:00 window."""
        timestamp = captured_at.timestamp()
        self._expire_wait_if_needed(timestamp)
        if not self._is_active_window(captured_at):
            return
        if self._awaiting_intent is not None:
            return
        if self._next_move_at is None:
            self._next_move_at = timestamp
        if timestamp < self._next_move_at:
            return
        if self._movement_target(captured_at) is None:
            return
        event = self._mock_tick(captured_at)
        receipt = self._workspace.publish(event)
        if receipt.disposition not in {
            IngestDisposition.ACCEPTED,
            IngestDisposition.COALESCED,
            IngestDisposition.DUPLICATE,
        }:
            # Retry on the next clock pulse without spinning the coordinator.
            self._next_move_at = timestamp + 1.0

    def drain(self, captured_at: UTCDateTime) -> bool:
        """Handle at most one embodied frame without invoking the model."""
        if self._workspace.metrics().critical_event_count > 0:
            # Critical physical facts remain available to the normal Brain
            # path; the Mock gate must never absorb them.
            return False
        metrics = self._workspace.metrics()
        if metrics.latest_ingest_seq == 0:
            return False
        turn_id = TurnId(f"mock-wander-turn-{uuid4().hex}")
        try:
            frame = self._workspace.claim_frame(
                metrics.latest_ingest_seq,
                turn_id=turn_id,
                reason=TriggerReason.AUTONOMOUS,
                captured_at=captured_at,
                source_domain=SourceDomain.EMBODIED,
            )
        except FrameLifecycleError as error:
            if error.reason == "no perception writes are available":
                return False
            raise

        try:
            terminal_seen = self._handle_terminal_feedback(frame, captured_at)
            if not terminal_seen:
                self._maybe_issue_move(frame, captured_at)
        except Exception as error:  # noqa: BLE001 - frame owns replay semantics
            self._workspace.release(frame.frame_id, turn_id, type(error).__name__)
            return False
        self._workspace.commit(frame.frame_id, turn_id)
        return True

    def _maybe_issue_move(self, frame: TurnFrame, captured_at: UTCDateTime) -> None:
        if self._awaiting_intent is not None:
            return
        if not self._is_active_window(captured_at):
            return
        timestamp = captured_at.timestamp()
        if self._next_move_at is None:
            self._next_move_at = timestamp
        if timestamp < self._next_move_at:
            return
        capabilities = self._context_source.capabilities(captured_at)
        target = self._movement_target_from(capabilities)
        if target is None:
            return
        event_ids = tuple(
            item.meta.event_id
            for item in frame.events + frame.state_updates + frame.media_samples
        )
        if not event_ids:
            return
        intent_id = IntentId(f"mock-wander-intent-{uuid4().hex}")
        turn_id = TurnId(f"mock-wander-turn-{uuid4().hex}")
        deadline = captured_at + timedelta(seconds=30)
        plan = DecisionPlan(
            plan_id=PlanId(f"mock-wander-plan-{uuid4().hex}"),
            turn_id=turn_id,
            frame_id=frame.frame_id,
            context_revision=frame.revision,
            capability_revision=capabilities.revision,
            created_at=captured_at,
            deadline=deadline,
            cause_event_ids=event_ids,
            intents=(
                CapabilityIntent(
                    type="capability",
                    intent_id=intent_id,
                    cause_event_ids=event_ids,
                    dependency_ids=(),
                    deadline=deadline,
                    cancel_policy=CancelPolicy.IF_NOT_STARTED,
                    category="world",
                    capability_id="move.to",
                    arguments={"anchor_id": target},
                ),
            ),
        )
        decision = govern_decision(frame, plan)
        accepted = self._plan_sink.accept(decision)
        if accepted:
            self._awaiting_intent = intent_id
            self._awaiting_deadline = timestamp + self._action_timeout_seconds
            self._last_target = target
            self._next_move_at = timestamp + self._next_interval()
        else:
            # Router rejection is already observable at its own boundary.
            # Retry later after capabilities or Runtime state can change.
            self._next_move_at = timestamp + 1.0

    def _handle_terminal_feedback(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> bool:
        for event in frame.events:
            payload = event.payload
            if not isinstance(payload, PhysicalPayload):
                continue
            if payload.modality is not PhysicalModality.PROPRIOCEPTION:
                continue
            fields = {
                key.strip(): value.strip()
                for part in payload.content.split(";")
                if "=" in part
                for key, value in (part.split("=", 1),)
            }
            if (
                fields.get("action") is None
                or fields.get("status") not in self._TERMINAL_STATUSES
            ):
                continue
            intent_id = fields.get("intent")
            if (
                self._awaiting_intent is not None
                and intent_id is not None
                and intent_id != str(self._awaiting_intent)
            ):
                continue
            self._awaiting_intent = None
            self._awaiting_deadline = None
            self._next_move_at = captured_at.timestamp() + self._next_interval()
            return True
        return False

    def _expire_wait_if_needed(self, timestamp: float) -> None:
        if (
            self._awaiting_intent is not None
            and self._awaiting_deadline is not None
            and timestamp >= self._awaiting_deadline
        ):
            self._awaiting_intent = None
            self._awaiting_deadline = None
            self._next_move_at = timestamp

    def _movement_target(self, captured_at: UTCDateTime) -> Optional[str]:
        return self._movement_target_from(
            self._context_source.capabilities(captured_at)
        )

    def _movement_target_from(
        self,
        capabilities: EffectiveCapabilities,
    ) -> Optional[str]:
        body = capabilities.current_body
        if body is None or not self._supports_move(body.actions):
            return None
        target_capability_id = (
            "move.to" if "move.to" in capabilities.world_capabilities else None
        )
        if target_capability_id is None:
            return None
        descriptor = next(
            (
                item
                for item in capabilities.capability_catalog
                if item.category == "world"
                and item.capability_id == target_capability_id
            ),
            None,
        )
        if descriptor is None:
            return None
        properties = descriptor.argument_schema.get("properties")
        if not isinstance(properties, Mapping):
            return None
        anchor = properties.get("anchor_id")
        if not isinstance(anchor, Mapping):
            return None
        values = anchor.get("enum")
        if not isinstance(values, (list, tuple)):
            return None
        targets = tuple(
            value for value in values if isinstance(value, str) and value.strip()
        )
        if not targets:
            return None
        # The Nest catalog also contains door/portal markers.  They are valid
        # semantic references, but are not guaranteed to be navigable landing
        # points in every Godot room.  The autonomous wander policy stays in
        # room activity points; explicit model ``move.to`` calls can still use
        # any catalogued target and receive the real Runtime result.
        wander_targets = (
            tuple(
                value
                for value in targets
                if value.endswith("/activity") or "/chair-" in value
            )
            or targets
        )
        choices = tuple(value for value in wander_targets if value != self._last_target)
        return self._rng.choice(choices or wander_targets)

    @staticmethod
    def _supports_move(actions: tuple[str, ...]) -> bool:
        return "*" in actions or any(
            action in actions
            for action in ("move_to_anchor", "body.move_to_anchor", "move.forward")
        )

    @staticmethod
    def _is_active_window(captured_at: UTCDateTime) -> bool:
        return 6 <= captured_at.astimezone().hour < 24

    def _next_interval(self) -> float:
        return self._rng.uniform(self._minimum_interval, self._maximum_interval)

    def _mock_tick(self, captured_at: UTCDateTime) -> PerceptionEvent:
        body = self._context_source.capabilities(captured_at).current_body
        if body is None:
            raise RuntimeError("mock embodied tick requires a current Body")
        event_id = EventId(f"mock-wander-tick-{uuid4().hex}")
        return PerceptionEvent(
            meta=MessageMeta(
                event_id=event_id,
                elfie_id=self._elfie_id,
                source=ActorRef(
                    actor_id=ActorId(f"{self._elfie_id}:embodied-mock"),
                    source_kind="internal",
                ),
                occurred_at=captured_at,
                received_at=captured_at,
                trace_id=TraceId(f"mock-wander:{event_id}"),
                priority=Priority.LOW,
            ),
            payload=PhysicalPayload(
                type="physical",
                body_id=body.body_id,
                body_generation=body.body_generation,
                modality=PhysicalModality.PROPRIOCEPTION,
                content=self._MOCK_TICK_CONTENT,
            ),
            salience=0.1,
        )


__all__ = ("EmbodiedInputMode", "EmbodiedMockController")
