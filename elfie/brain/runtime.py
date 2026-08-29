"""Lifecycle owner for one Elfie's private asynchronous Brain loop."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Optional, Tuple

from elfie.brain.activity.preflight import ActivityPreflightService
from elfie.brain.activity.system import (
    ActivityRecord,
    ActivityState,
    ActivityStateEvent,
    ActivityStepKind,
    ActivityStorePort,
    InMemoryActivityStore,
    activity_scope_for_record,
    activity_state_event_to_perception,
)
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.emotion.appraiser import BrainClockPulse, EmotionAppraiser
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.journal import (
    BrainJournal,
    BrainJournalEntry,
    BrainJournalPort,
    InMemoryBrainJournal,
    reconciliation_fact_to_perception,
)
from elfie.brain.memory import MemorySystem
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.context_source import BrainContextProvider
from elfie.brain.reasoning.coordinator import BrainCoordinator
from elfie.brain.reasoning.decision_decoder import DecisionPlanDecoder
from elfie.brain.reasoning.decision_types import (
    DecisionIntent,
    ExpressionIntent,
    MessageIntent,
    MotionIntent,
    NoOpIntent,
    PersistentActivityRequest,
    SpeechIntent,
    TurnDecision,
)
from elfie.brain.reasoning.execution_ports import IntentExecutor
from elfie.brain.reasoning.execution_router import OutputRouter
from elfie.brain.reasoning.execution_types import ExecutionReceipt
from elfie.brain.reasoning.internal_execution import PersistentActivityRequestExecutor
from elfie.brain.reasoning.model_port import ModelPort
from elfie.brain.reasoning.run import ReasoningRunResult
from elfie.brain.reasoning.settlement import TurnSettlement
from elfie.brain.reasoning.skills import SkillManager
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.brain.reasoning.turn_outcome import TurnOutcome
from elfie.brain.reasoning.worker import ReasoningWorker
from elfie.brain.selfhood.contracts import ProfileAnchorSnapshot, SelfhoodSnapshot
from elfie.brain.state_lifecycle import StateCommitStatus
from elfie.brain.workspace.contracts import ExecutionStatus
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    TurnId,
    UTCDateTime,
)

logger = logging.getLogger("elfie.brain.runtime")


class BrainRuntime:
    """Own Brain coordinator, worker, decision boundary, and shutdown order."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: EventWorkspace,
        emotion: EmotionSystem,
        homeostasis: EnergySystem,
        context: BrainContextProvider,
        memory: MemorySystem,
        clock: Callable[[], UTCDateTime],
        model_port: ModelPort,
        tool_port: ToolPort | None = None,
        skills: SkillManager,
        body_executor: IntentExecutor,
        message_executor: IntentExecutor,
        internal_executor: IntentExecutor,
        activity_store: ActivityStorePort | None = None,
        journal_store: BrainJournalPort | None = None,
        restore_clock: Callable[[UTCDateTime], None] | None = None,
    ) -> None:
        self._clock = clock
        self._elfie_id = elfie_id
        self.context = context
        self.activity_store = activity_store or InMemoryActivityStore()
        self._journal_store = journal_store or InMemoryBrainJournal()
        self._restore_clock = restore_clock or (lambda _captured_at: None)
        self._journal = BrainJournal(
            elfie_id=elfie_id,
            store=self._journal_store,
            clock=clock,
        )
        self._activity_lock = Lock()
        self._interaction_lock = Lock()
        activity_preflight = ActivityPreflightService(
            store=self.activity_store,
            clock=clock,
            capabilities=context.current,
            available_budget=homeostasis.activity_budget_available,
            target_resolver=context.can_reach_actor,
        )
        activity_executor = PersistentActivityRequestExecutor(
            activity_preflight,
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
            journal=self._journal,
        )
        worker = ReasoningWorker(
            model_port=model_port,
            decoder=DecisionPlanDecoder(),
            tool_port=tool_port,
            activity_preflight=activity_preflight,
        )
        settlement = TurnSettlement(
            memory,
            orientation=context.commit_orientation_candidate,
        )
        self.coordinator = BrainCoordinator(
            elfie_id=elfie_id,
            workspace=workspace,
            emotion=emotion,
            homeostasis=homeostasis,
            appraiser=EmotionAppraiser(),
            context_source=context,
            reasoning_worker=worker,
            plan_sink=self.router,
            settlement=settlement,
            initial_timestamp=clock().timestamp(),
            allowed_tools=skills.allowed_tool_keys(),
            motivation_blocked=self._motivation_blocked,
            consolidation_blocked=self._consolidation_blocked,
            journal=self._journal,
            on_outcome=self._persist_after_outcome,
            on_state_change=self._save_continuity,
        )
        self._started = False
        self._workspace = workspace
        self._emotion = emotion
        self._homeostasis = homeostasis

    def start(self) -> None:
        if self._started:
            return
        checkpoint_was_rebuilt = False
        try:
            try:
                checkpoint = self._journal_store.load_checkpoint()
            except (TypeError, ValueError) as error:
                # v1 emotion state is intentionally incompatible with the
                # six-channel initial release.  Start from fresh defaults and
                # overwrite the checkpoint after the lifecycle is healthy.
                logger.warning(
                    "Discarding incompatible Brain checkpoint during v1 rebuild: %s",
                    type(error).__name__,
                )
                checkpoint = None
                checkpoint_was_rebuilt = True
            if checkpoint is not None:
                try:
                    self._restore_clock(checkpoint.captured_at)
                    self.restore_continuity(checkpoint)
                except (TypeError, ValueError) as error:
                    logger.warning(
                        "Discarding incompatible Brain checkpoint during v1 rebuild: %s",
                        type(error).__name__,
                    )
                    checkpoint_was_rebuilt = True
            recovered = self._reconcile_interrupted_work()
            self.router.start()
            self.coordinator.start()
            if checkpoint_was_rebuilt:
                self._save_continuity()
            if recovered:
                self.coordinator.notify_perception()
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

    def motivation_snapshot(self):
        """Expose the current fixed-drive state for Lab/Observer inspection."""
        return self.context.motivation_snapshot()

    def consolidation_snapshot(self):
        """Expose bounded quiet-window cognition for Lab/Observer inspection."""
        return self.context.consolidation_snapshot()

    def continuity_checkpoint(self) -> BrainContinuityCheckpoint:
        """Capture one checkpoint for the Stage 4C continuous state owners."""
        return BrainContinuityCheckpoint(
            captured_at=self._clock(),
            emotion=self._emotion.checkpoint(),
            energy=self._homeostasis.checkpoint(),
            memory=self.context.memory_checkpoint(),
            orientation=self.context.orientation_checkpoint(),
            selfhood=self.context.selfhood_checkpoint(),
            motivation=self.context.motivation_checkpoint(),
            consolidation=self.context.consolidation_checkpoint(),
            conversation=self.context.conversation_checkpoint(),
        )

    def restore_continuity(self, checkpoint: BrainContinuityCheckpoint) -> None:
        """Prevalidate and restore all continuous owners while Brain is stopped."""
        if self._started:
            raise RuntimeError("cannot restore Brain continuity while it is running")
        self._emotion.validate_checkpoint(checkpoint.emotion)
        self._homeostasis.validate_checkpoint(checkpoint.energy)
        self.context.validate_memory_checkpoint(checkpoint.memory)
        self.context.validate_orientation_checkpoint(checkpoint.orientation)
        self.context.validate_selfhood_checkpoint(checkpoint.selfhood)
        self.context.validate_motivation_checkpoint(checkpoint.motivation)
        self.context.validate_consolidation_checkpoint(checkpoint.consolidation)
        self.context.validate_conversation_checkpoint(checkpoint.conversation)
        self._emotion.restore(checkpoint.emotion)
        self._homeostasis.restore(checkpoint.energy)
        self.context.restore_memory_checkpoint(checkpoint.memory)
        self.context.restore_orientation_checkpoint(checkpoint.orientation)
        self.context.restore_selfhood_checkpoint(checkpoint.selfhood)
        self.context.restore_motivation_checkpoint(checkpoint.motivation)
        self.context.restore_consolidation_checkpoint(checkpoint.consolidation)
        self.context.restore_conversation_checkpoint(checkpoint.conversation)

    def decision(self, turn_id: TurnId) -> Optional[TurnDecision]:
        return self.router.decision(turn_id)

    def reasoning(self, turn_id: TurnId) -> Optional[ReasoningRunResult]:
        return self.coordinator.reasoning(turn_id)

    def activities(self):
        """Return committed Activity records for Brain/Lab observation."""
        return self.activity_store.list()

    def journal_entries(self) -> Tuple[BrainJournalEntry, ...]:
        """Return append-only causal facts for diagnostics and recovery tests."""
        return self._journal.entries()

    def _reconcile_interrupted_work(self) -> bool:
        """Never replay uncertain side effects after restart; surface them as facts."""
        recovered = False
        for fact in self._journal.reconcile_unfinished():
            self._workspace.publish(
                reconciliation_fact_to_perception(
                    fact,
                    elfie_id=self._elfie_id,
                    occurred_at=self._clock(),
                )
            )
            recovered = True
        for record in self.activity_store.list():
            if record.state is not ActivityState.RUNNING:
                continue
            occurred_at = max(self._clock(), record.updated_at)
            try:
                event = self.activity_store.transition(
                    record.activity_id,
                    expected_revision=record.revision,
                    target=ActivityState.PAUSED,
                    now=occurred_at,
                    reason="restart_reconciliation_required",
                )
            except Exception:
                continue
            current = self.activity_store.get(record.activity_id)
            if current is None:
                continue
            self._journal.record_activity(
                current,
                detail="restart_reconciliation_required",
            )
            self._workspace.publish(
                activity_state_event_to_perception(
                    event,
                    elfie_id=self._elfie_id,
                    response_scope=activity_scope_for_record(current),
                )
            )
            recovered = True
        return recovered

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
                    self._journal.record_activity(current, detail="activity_due")
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
        self._settle_motivation_receipt(intent, receipt)
        self._settle_consolidation_receipt(intent, receipt)
        if receipt.status is ExecutionStatus.COMPLETED and isinstance(
            intent, MessageIntent
        ):
            self._record_completed_interaction(intent, receipt)
        if receipt.status in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLED,
        }:
            self._save_continuity()
        if isinstance(intent, PersistentActivityRequest):
            record = self.activity_store.get(intent.draft.activity_id)
            if record is not None:
                self._journal.record_activity(
                    record,
                    detail=f"request_receipt:{receipt.receipt_id}",
                )
            return
        if receipt.status is not ExecutionStatus.COMPLETED:
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
                current = self.activity_store.get(record.activity_id)
                if current is not None:
                    self._journal.record_activity(
                        current,
                        detail=f"step_receipt:{receipt.receipt_id}",
                    )

    def _record_completed_interaction(
        self,
        intent: MessageIntent,
        receipt: ExecutionReceipt,
    ) -> None:
        """Join and optionally remember only an actually delivered owner reply."""
        with self._interaction_lock:
            interaction = self.context.record_completed_reply(
                channel_id=intent.channel_id,
                conversation_id=intent.conversation_id,
                reply_event_id=EventId(f"elfie-reply:{intent.intent_id}"),
                sender=ActorRef(
                    actor_id=ActorId(str(self._elfie_id)),
                    source_kind="elfie",
                ),
                occurred_at=receipt.occurred_at,
                content=intent.content,
                cause_event_ids=intent.cause_event_ids,
                receipt_id=receipt.receipt_id,
            )
            if interaction is None:
                return
            try:
                committed = self.context.commit_completed_interaction(interaction)
                if committed is None:
                    return
                if committed.status not in {
                    StateCommitStatus.COMMITTED,
                    StateCommitStatus.DUPLICATE,
                }:
                    logger.warning(
                        "completed interaction memory was not committed: %s",
                        committed.reason or committed.status.value,
                    )
            except (OSError, RuntimeError, ValueError) as error:
                logger.warning(
                    "completed interaction memory commit failed: %s",
                    type(error).__name__,
                )

    def _settle_motivation_receipt(
        self,
        intent: DecisionIntent,
        receipt: ExecutionReceipt,
    ) -> None:
        """Mark one bounded drive handled after its Internal Turn settles."""
        if receipt.status is not ExecutionStatus.COMPLETED or not isinstance(
            intent, (NoOpIntent, PersistentActivityRequest)
        ):
            return
        candidate_id = next(
            (
                event_id
                for event_id in intent.cause_event_ids
                if str(event_id).startswith("motivation:recovery:")
            ),
            None,
        )
        if candidate_id is not None:
            self.context.settle_motivation(
                candidate_id,
                now=receipt.occurred_at,
                success=True,
            )

    def _settle_consolidation_receipt(
        self,
        intent: DecisionIntent,
        receipt: ExecutionReceipt,
    ) -> None:
        """Commit memory整理 only after its inert Internal Turn settles."""
        if not isinstance(intent, (NoOpIntent, PersistentActivityRequest)):
            return
        terminal = {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLED,
        }
        if receipt.status not in terminal:
            return
        candidate_id = next(
            (
                event_id
                for event_id in intent.cause_event_ids
                if str(event_id).startswith("consolidation:")
            ),
            None,
        )
        if candidate_id is not None:
            self.context.settle_consolidation(
                candidate_id,
                now=receipt.occurred_at,
                success=receipt.status is ExecutionStatus.COMPLETED,
            )

    def _motivation_blocked(self) -> bool:
        """Treat pending external work as higher priority than a drive."""
        with self._activity_lock:
            active_activity = any(
                record.state
                in {
                    ActivityState.VALIDATED,
                    ActivityState.WAITING,
                    ActivityState.RUNNING,
                    ActivityState.PAUSED,
                }
                for record in self.activity_store.list()
            )
        return active_activity or self._workspace.metrics().reliable_event_count > 0

    def _consolidation_blocked(self) -> bool:
        """Do not start quiet-window整理 while foreground work is pending."""
        with self._activity_lock:
            active_activity = any(
                record.state
                in {
                    ActivityState.VALIDATED,
                    ActivityState.WAITING,
                    ActivityState.RUNNING,
                    ActivityState.PAUSED,
                }
                for record in self.activity_store.list()
            )
        return active_activity or self._workspace.metrics().reliable_event_count > 0

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
        self._save_continuity()
        self._started = False

    def _persist_after_outcome(self, _outcome: TurnOutcome) -> None:
        self._save_continuity()

    def _save_continuity(self) -> None:
        self._journal_store.save_checkpoint(self.continuity_checkpoint())

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
