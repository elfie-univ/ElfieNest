"""Lifecycle owner for one Elfie's private asynchronous Brain loop."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Optional, Tuple

from elfie.brain.activity import (
    ActivityRecord,
    ActivityState,
    ActivityStateEvent,
    ActivityStepKind,
    ActivityStorePort,
    InMemoryActivityStore,
    activity_scope_for_record,
    activity_state_event_to_perception,
)
from elfie.brain.context_source import BrainContextState
from elfie.brain.context_types import (
    OrientationSnapshot,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.coordinator import BrainCoordinator
from elfie.brain.cortical_worker import CorticalWorker
from elfie.brain.decision_decoder import DecisionPlanDecoder
from elfie.brain.decision_types import (
    DecisionIntent,
    ExpressionIntent,
    MessageIntent,
    MotionIntent,
    PersistentActivityIntent,
    SpeechIntent,
    TurnDecision,
)
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.internal_output import PersistentActivityIntentExecutor
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.output_ports import IntentExecutor
from elfie.brain.output_router import OutputRouter
from elfie.brain.output_types import ExecutionReceipt
from elfie.brain.perception_types import ExecutionStatus
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.reasoning import ReasoningRunResult
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.brain.turn_outcome import TurnOutcome
from elfie.message_types import ElfieId, TurnId, UTCDateTime


class BrainRuntime:
    """Own Brain coordinator, worker, decision boundary, and shutdown order."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: PerceptualWorkspace,
        emotion: EmotionSystem,
        homeostasis: HypothalamusEnergy,
        context: BrainContextState,
        clock: Callable[[], UTCDateTime],
        model_port: ModelPort,
        tool_port: ToolPort | None = None,
        skills: SkillManager,
        body_executor: IntentExecutor,
        message_executor: IntentExecutor,
        internal_executor: IntentExecutor,
        activity_store: ActivityStorePort | None = None,
    ) -> None:
        self._clock = clock
        self._elfie_id = elfie_id
        self.context = context
        self.activity_store = activity_store or InMemoryActivityStore()
        self._activity_lock = Lock()
        activity_executor = PersistentActivityIntentExecutor(
            self.activity_store,
            clock=clock,
            elfie_id=elfie_id,
            trigger_sink=workspace,
            on_trigger=lambda: self.coordinator.notify_perception(),
        )
        self.router = OutputRouter(
            elfie_id=elfie_id,
            capabilities=context,
            perception_sink=workspace,
            body_executor=body_executor,
            message_executor=message_executor,
            internal_executor=internal_executor,
            activity_executor=activity_executor,
            clock=clock,
            receipt_handler=self._settle_activity_receipt,
        )
        worker = CorticalWorker(
            model_port=model_port,
            decoder=DecisionPlanDecoder(),
            tool_port=tool_port,
        )
        self.coordinator = BrainCoordinator(
            elfie_id=elfie_id,
            workspace=workspace,
            emotion=emotion,
            homeostasis=homeostasis,
            appraiser=LimbicAppraiser(),
            context_source=context,
            cortical_worker=worker,
            plan_sink=self.router,
            initial_timestamp=clock().timestamp(),
            allowed_tools=skills.allowed_tool_keys(),
        )
        self._started = False
        self._workspace = workspace
        self._emotion = emotion
        self._homeostasis = homeostasis

    def start(self) -> None:
        if self._started:
            return
        try:
            self.router.start()
            self.coordinator.start()
        except (OSError, RuntimeError):
            try:
                self.coordinator.stop()
            except RuntimeError:
                pass
            try:
                self.coordinator.join()
            except RuntimeError:
                pass
            try:
                self.router.stop()
            except RuntimeError:
                pass
            try:
                self.router.join()
            except RuntimeError:
                pass
            self._started = False
            raise
        self._started = True

    def post_clock(self, timestamp: float) -> None:
        self._wake_due_activities(datetime.fromtimestamp(timestamp, timezone.utc))
        self.coordinator.post_clock(BrainClockPulse(timestamp=timestamp))

    def notify_perception(self, *, urgent_reason: Optional[str] = None) -> None:
        self.coordinator.notify_perception(urgent_reason=urgent_reason)

    def outcomes(self) -> Tuple[TurnOutcome, ...]:
        return self.coordinator.outcomes()

    def wait_for_outcome_count(self, count: int, *, timeout: float) -> None:
        self.coordinator.wait_for_outcome_count(count, timeout=timeout)

    def wait_for_output(self, turn_id: TurnId, *, timeout: float) -> None:
        self.router.wait_for_turn(turn_id, timeout=timeout)

    def execution_receipts(self, turn_id: TurnId) -> Tuple[ExecutionReceipt, ...]:
        return self.router.receipts(turn_id)

    def orientation_snapshot(self) -> OrientationSnapshot:
        """Expose the latest committed orientation for Lab/Observer inspection."""
        return self.context.orientation_snapshot()

    def selfhood_snapshot(self) -> SelfhoodSnapshot:
        """Expose the latest committed mutable self-model for inspection."""
        return self.context.selfhood_snapshot()

    def profile_anchors(self) -> ProfileAnchorSnapshot:
        """Expose the immutable Profile projection used by Brain context."""
        return self.context.profile_anchors(self._clock())

    def continuity_checkpoint(self) -> BrainContinuityCheckpoint:
        """Capture one checkpoint for the Stage 4C continuous state owners."""
        return BrainContinuityCheckpoint(
            captured_at=self._clock(),
            emotion=self._emotion.checkpoint(),
            energy=self._homeostasis.checkpoint(),
            memory=self.context.memory_checkpoint(),
        )

    def restore_continuity(self, checkpoint: BrainContinuityCheckpoint) -> None:
        """Restore Emotion/Energy/Memory atomically while Brain is stopped."""
        if self._started:
            raise RuntimeError("cannot restore Brain continuity while it is running")
        current = self.continuity_checkpoint()
        self._emotion.validate_checkpoint(checkpoint.emotion)
        self._homeostasis.validate_checkpoint(checkpoint.energy)
        self.context.validate_memory_checkpoint(checkpoint.memory)
        try:
            self._emotion.restore(checkpoint.emotion)
            self._homeostasis.restore(checkpoint.energy)
            self.context.restore_memory_checkpoint(checkpoint.memory)
        except Exception:
            self._emotion.restore(current.emotion)
            self._homeostasis.restore(current.energy)
            self.context.restore_memory_checkpoint(current.memory)
            raise

    def decision(self, turn_id: TurnId) -> Optional[TurnDecision]:
        return self.router.decision(turn_id)

    def reasoning(self, turn_id: TurnId) -> Optional[ReasoningRunResult]:
        return self.coordinator.reasoning(turn_id)

    def activities(self):
        """Return committed Activity records for Brain/Lab observation."""
        return self.activity_store.list()

    def _wake_due_activities(self, now: datetime) -> None:
        """Turn due durable work into one deduplicable Internal event."""
        events: list[tuple[ActivityStateEvent, ActivityRecord]] = []
        with self._activity_lock:
            for record in self.activity_store.list():
                if (
                    record.state is not ActivityState.WAITING
                    or record.next_wakeup_at is None
                    or record.next_wakeup_at > now
                ):
                    continue
                try:
                    event = self.activity_store.transition(
                        record.activity_id,
                        expected_revision=record.revision,
                        target=ActivityState.RUNNING,
                        now=now,
                        reason="activity_due",
                    )
                except Exception:
                    continue
                current = self.activity_store.get(record.activity_id)
                if current is not None:
                    events.append((event, current))
        for event, record in events:
            self._workspace.publish(
                activity_state_event_to_perception(
                    event,
                    elfie_id=self._elfie_id,
                    response_scope=activity_scope_for_record(record),
                )
            )
        if events:
            self.coordinator.notify_perception()

    def _settle_activity_receipt(
        self,
        _plan,
        intent: DecisionIntent,
        receipt: ExecutionReceipt,
    ) -> None:
        """Bind a child external receipt to the Activity step that requested it."""
        if receipt.status is not ExecutionStatus.COMPLETED or isinstance(
            intent, PersistentActivityIntent
        ):
            return
        if not isinstance(
            intent, (MessageIntent, SpeechIntent, MotionIntent, ExpressionIntent)
        ):
            return
        with self._activity_lock:
            records = self.activity_store.list()
            for record in records:
                if record.state is not ActivityState.RUNNING:
                    continue
                step = next(
                    (
                        item
                        for item in record.draft.steps
                        if item.step_id == record.current_step_id
                    ),
                    None,
                )
                if step is None or not _activity_step_matches_intent(step.kind, intent):
                    continue
                trigger_id = (
                    f"activity-event:{record.activity_id}:"
                    f"{record.revision}:{record.state.value}"
                )
                if trigger_id not in {str(item) for item in intent.cause_event_ids}:
                    continue
                try:
                    self.activity_store.settle_step(
                        record.activity_id,
                        expected_revision=record.revision,
                        receipt_id=receipt.receipt_id,
                        now=receipt.occurred_at,
                        success=True,
                        reason=f"step_receipt:{receipt.receipt_id}",
                    )
                except Exception:
                    continue

    def stop(self) -> None:
        if not self._started:
            return
        self._workspace.stop()
        self.coordinator.stop()
        self.router.stop()

    def join(self) -> None:
        if not self._started:
            return
        self.coordinator.join()
        self.router.join()
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self.coordinator.is_alive


def _activity_step_matches_intent(
    kind: ActivityStepKind,
    intent: DecisionIntent,
) -> bool:
    if kind is ActivityStepKind.COMMUNICATION:
        return isinstance(intent, MessageIntent)
    if kind is ActivityStepKind.NERVOUS_SYSTEM:
        return isinstance(intent, (SpeechIntent, MotionIntent, ExpressionIntent))
    return False


__all__ = ("BrainRuntime",)
