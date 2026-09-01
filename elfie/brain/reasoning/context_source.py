"""Read-only aggregate over independently owned Brain context sources."""

from __future__ import annotations

from threading import Lock
from typing import Callable, Mapping, Optional, Tuple

from elfie.brain.activity.context import ActivityContext, ActivityContextReader
from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.consolidation.system import (
    CognitiveConsolidationCandidate,
    CognitiveConsolidationCheckpoint,
    CognitiveConsolidationSystem,
)
from elfie.brain.emotion.contracts import (
    AppraisalRelevance,
    EmotionSnapshot,
    TrustedAppraisalScope,
)
from elfie.brain.memory import EpisodicMemoryCandidate
from elfie.brain.memory.memory_records import ClosedEpisode, MemoryUseProposal
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.motivation.system import (
    MotivationCheckpoint,
    MotivationSystem,
    RecoveryDriveCandidate,
)
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_types import (
    CompletedConversationInteraction,
    ConversationContext,
    ConversationContextCheckpoint,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.reasoning.memory_context import (
    ReasoningMemoryBridge,
    ReasoningMemoryTurn,
)
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection, SelfhoodState
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCommitReceipt,
    StateCommitStatus,
)
from elfie.brain.workspace.contracts import ExecutionStatus, SocialPayload, TurnFrame
from elfie.message_types import ActorRef, EventId, IntentId, TurnId, UTCDateTime

CapabilityReader = Callable[
    [UTCDateTime, Mapping[str, Tuple[str, ...]]], EffectiveCapabilities
]


class BrainContextProvider:
    """Compose owner snapshots without constructing or committing mental owners.

    The Reasoning Context Workspace owns its bounded working history; durable
    Memory and versioned mental-state changes are emitted as settlement candidates.
    """

    def __init__(
        self,
        *,
        memory: ReasoningMemoryBridge,
        conversations: ReasoningContextWorkspace,
        activities: ActivityContextReader,
        capability_reader: CapabilityReader,
        clock: Callable[[], UTCDateTime],
        orientation: OrientationSystem,
        selfhood: SelfhoodSystem,
        motivation: MotivationSystem,
        consolidation: CognitiveConsolidationSystem,
    ) -> None:
        self._memory = memory
        self._conversations = conversations
        self._activities = activities
        self._capability_reader = capability_reader
        self._clock = clock
        self._orientation = orientation
        self._selfhood = selfhood
        self._motivation = motivation
        self._consolidation = consolidation
        self._memory_lock = Lock()
        self._state_lock = Lock()

    def conversation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        return self._conversations.observe(frame, captured_at)

    def memory_turn(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> ReasoningMemoryTurn:
        with self._memory_lock:
            return self._memory.open_turn(frame, emotion, captured_at)

    def memory_candidates(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> Tuple[EpisodicMemoryCandidate, ...]:
        with self._memory_lock:
            return self._memory.candidates(frame, emotion, captured_at)

    def emotion_appraisal_scopes(
        self,
        frame: TurnFrame,
    ) -> tuple[TrustedAppraisalScope, ...]:
        """Bind empathic scope only to a trusted source actor relationship."""

        scopes: list[TrustedAppraisalScope] = []
        with self._memory_lock:
            for event in frame.events:
                payload = event.payload
                if not isinstance(payload, SocialPayload):
                    continue
                relationship = self._memory.relationship_importance(
                    str(payload.sender.actor_id),
                    owner=payload.sender.source_kind == "owner",
                )
                if relationship is None:
                    continue
                scopes.append(
                    TrustedAppraisalScope(
                        scope_id=f"appraisal:{event.meta.event_id}:indirect",
                        cause_event_id=event.meta.event_id,
                        relevance=AppraisalRelevance.INDIRECT,
                        related_actor_id=str(payload.sender.actor_id),
                        relationship_revision=relationship.revision,
                        relationship_weight=relationship.importance,
                    )
                )
        return tuple(scopes)

    def flush_pending_handoffs(
        self,
        capture: Callable[[tuple[ClosedEpisode, ...]], tuple[StateCommitReceipt, ...]],
    ) -> tuple[StateCommitReceipt, ...]:
        """Run the sole retryable Context Workspace -> Memory handoff path."""
        episodes = self._conversations.pending_closed_episodes()
        if not episodes:
            return ()
        receipts = capture(episodes)
        failed = tuple(
            receipt
            for receipt in receipts
            if receipt.status
            not in {StateCommitStatus.COMMITTED, StateCommitStatus.DUPLICATE}
        )
        if failed:
            reasons = ",".join(
                receipt.reason or receipt.status.value for receipt in failed
            )
            raise RuntimeError(f"Episode source capture failed: {reasons}")
        accepted_ids = {
            str(receipt.candidate_id)
            for receipt in receipts
            if receipt.status
            in {StateCommitStatus.COMMITTED, StateCommitStatus.DUPLICATE}
        }
        self._conversations.ack_closed_episodes(
            tuple(
                episode.episode_id
                for episode in episodes
                if episode.episode_id in accepted_ids
            )
        )
        return receipts

    def memory_checkpoint(self):
        with self._memory_lock:
            return self._memory.checkpoint()

    def restore_memory_checkpoint(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.restore(checkpoint)

    def submit_memory_use_proposal(
        self,
        frame_id: str,
        proposal: MemoryUseProposal,
    ) -> bool:
        """Settle a model's bounded references against the exact Recall frame."""
        with self._memory_lock:
            return self._memory.submit_use_proposal(EventId(frame_id), proposal)

    def validate_memory_checkpoint(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.validate_checkpoint(checkpoint)

    def prepare_reply(self, **values) -> bool:
        return self._conversations.prepare_reply(**values)

    def settle_reply(
        self,
        *,
        intent_id: IntentId,
        status: ExecutionStatus,
        receipt_id: EventId,
        occurred_at: UTCDateTime,
        sender: ActorRef,
    ) -> CompletedConversationInteraction | None:
        return self._conversations.settle_reply(
            intent_id=intent_id,
            status=status,
            receipt_id=receipt_id,
            occurred_at=occurred_at,
            sender=sender,
        )

    def discard_pending_reply(
        self,
        intent_id: IntentId,
        *,
        occurred_at: UTCDateTime,
    ) -> bool:
        return self._conversations.discard_pending_reply(
            intent_id,
            occurred_at=occurred_at,
        )

    def pending_reply_ids(self) -> tuple[str, ...]:
        return self._conversations.pending_reply_ids()

    def conversation_checkpoint(self) -> ConversationContextCheckpoint:
        return self._conversations.checkpoint()

    def validate_conversation_checkpoint(
        self,
        checkpoint: ConversationContextCheckpoint,
    ) -> None:
        self._conversations.validate_checkpoint(checkpoint)

    def restore_conversation_checkpoint(
        self,
        checkpoint: ConversationContextCheckpoint,
    ) -> None:
        self._conversations.restore(checkpoint)

    def activities(self, captured_at: UTCDateTime) -> ActivityContext:
        return self._activities.read(captured_at)

    def capabilities(self, captured_at: UTCDateTime) -> EffectiveCapabilities:
        return self._capability_reader(
            captured_at,
            self._conversations.authorization_map(),
        )

    def current(self) -> EffectiveCapabilities:
        return self.capabilities(self._clock())

    def can_reach_actor(
        self,
        actor_id: str,
        channel_id: str,
        conversation_id: str,
    ) -> bool:
        return self._conversations.can_reach_actor(
            actor_id,
            channel_id,
            conversation_id,
        )

    def orientation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
        turn_id: TurnId,
        capabilities: EffectiveCapabilities,
    ) -> OrientationSnapshot:
        return self.orientation_candidate(
            frame,
            captured_at,
            turn_id,
            capabilities,
        ).value

    def orientation_candidate(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
        turn_id: TurnId,
        capabilities: EffectiveCapabilities,
    ) -> StateCandidate[OrientationSnapshot]:
        """Propose this Turn's orientation without mutating its owner."""
        active_activity = next(
            (
                item.activity_id
                for item in self._activities.read(captured_at).items
                if item.state.value in {"validated", "waiting", "running", "paused"}
            ),
            None,
        )
        return self._orientation.candidate(
            frame=frame,
            capabilities=capabilities,
            turn_id=turn_id,
            captured_at=captured_at,
            activity_id=(str(active_activity) if active_activity is not None else None),
        )

    def commit_orientation_candidate(
        self, candidate: StateCandidate[OrientationSnapshot]
    ) -> StateCommitReceipt:
        """Commit orientation only at the explicit Turn settlement boundary."""
        return self._orientation.commit(candidate)

    def orientation_snapshot(self) -> OrientationSnapshot:
        return self._orientation.snapshot()

    def orientation_checkpoint(self):
        return self._orientation.checkpoint()

    def validate_orientation_checkpoint(self, checkpoint) -> None:
        self._orientation.validate_checkpoint(checkpoint)

    def restore_orientation_checkpoint(self, checkpoint) -> None:
        self._orientation.restore(checkpoint)

    def selfhood(self, captured_at: UTCDateTime) -> SelfhoodPromptProjection:
        return self._selfhood.prompt_projection().model_copy(
            update={"captured_at": captured_at}
        )

    def selfhood_snapshot(self) -> SelfhoodState:
        return self._selfhood.snapshot()

    def motivation(self, captured_at: UTCDateTime) -> MotivationSnapshot:
        with self._state_lock:
            return self._motivation.snapshot(captured_at)

    def motivation_snapshot(self) -> MotivationSnapshot:
        return self.motivation(self._clock())

    def evaluate_motivation(
        self,
        *,
        energy: float,
        fatigue: float,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[RecoveryDriveCandidate]:
        with self._state_lock:
            return self._motivation.evaluate(
                energy=energy,
                fatigue=fatigue,
                sleeping=sleeping,
                now=now,
                blocked=blocked,
            )

    def settle_motivation(
        self,
        candidate_id: EventId,
        *,
        now: UTCDateTime,
        success: bool,
    ) -> bool:
        with self._state_lock:
            return self._motivation.mark_handled(
                candidate_id,
                now=now,
                success=success,
            )

    def motivation_checkpoint(self) -> MotivationCheckpoint:
        with self._state_lock:
            return self._motivation.checkpoint()

    def validate_motivation_checkpoint(self, checkpoint: MotivationCheckpoint) -> None:
        with self._state_lock:
            self._motivation.validate_checkpoint(checkpoint)

    def restore_motivation_checkpoint(self, checkpoint: MotivationCheckpoint) -> None:
        with self._state_lock:
            self._motivation.restore(checkpoint)

    def consolidation(self, captured_at: UTCDateTime) -> CognitiveConsolidationSnapshot:
        with self._state_lock:
            return self._consolidation.snapshot(captured_at)

    def consolidation_snapshot(self) -> CognitiveConsolidationSnapshot:
        return self.consolidation(self._clock())

    def evaluate_consolidation(
        self,
        *,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[CognitiveConsolidationCandidate]:
        with self._state_lock:
            return self._consolidation.evaluate(
                sleeping=sleeping,
                now=now,
                blocked=blocked,
            )

    def settle_consolidation(
        self,
        candidate_id: EventId,
        *,
        now: UTCDateTime,
        success: bool,
    ) -> bool:
        with self._state_lock:
            return self._consolidation.settle(
                candidate_id,
                now=now,
                success=success,
            )

    def consolidation_checkpoint(self) -> CognitiveConsolidationCheckpoint:
        with self._state_lock:
            return self._consolidation.checkpoint()

    def validate_consolidation_checkpoint(
        self,
        checkpoint: CognitiveConsolidationCheckpoint,
    ) -> None:
        with self._state_lock:
            self._consolidation.validate_checkpoint(checkpoint)

    def restore_consolidation_checkpoint(
        self,
        checkpoint: CognitiveConsolidationCheckpoint,
    ) -> None:
        with self._state_lock:
            self._consolidation.restore(checkpoint)


__all__ = ("BrainContextProvider", "CapabilityReader")
