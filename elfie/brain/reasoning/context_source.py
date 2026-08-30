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
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.memory.memory_records import ClosedEpisode
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
from elfie.brain.reasoning.conversation_context import ConversationContextStore
from elfie.brain.reasoning.memory_context import MemoryContextReader
from elfie.brain.selfhood.contracts import ProfileAnchorSnapshot, SelfhoodSnapshot
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.state_lifecycle import StateCandidate, StateCommitReceipt
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import EventId, TurnId, UTCDateTime

CapabilityReader = Callable[
    [UTCDateTime, Mapping[str, Tuple[str, ...]]], EffectiveCapabilities
]


class BrainContextProvider:
    """Compose owner snapshots without constructing or committing mental owners.

    ``ConversationContextStore.observe`` owns its bounded working history; durable
    Memory and versioned mental-state changes are emitted as settlement candidates.
    """

    def __init__(
        self,
        *,
        memory: MemoryContextReader,
        conversations: ConversationContextStore,
        activities: ActivityContextReader,
        capability_reader: CapabilityReader,
        clock: Callable[[], UTCDateTime],
        orientation: OrientationSystem,
        selfhood: SelfhoodSystem,
        motivation: MotivationSystem,
        consolidation: CognitiveConsolidationSystem,
        profile_anchors: ProfileAnchorSnapshot,
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
        self._profile_anchors = profile_anchors
        self._memory_lock = Lock()
        self._state_lock = Lock()

    def conversation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        return self._conversations.observe(frame, captured_at)

    def memory(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        with self._memory_lock:
            return self._memory.read(frame, emotion, captured_at)

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

    def pending_closed_episodes(self) -> tuple[ClosedEpisode, ...]:
        """Return upstream-closed Episodes awaiting source-first capture."""
        return self._conversations.pending_closed_episodes()

    def ack_closed_episodes(self, episode_ids: tuple[str, ...]) -> None:
        """Acknowledge Episodes after the Memory source write succeeds."""
        self._conversations.ack_closed_episodes(episode_ids)

    def memory_checkpoint(self):
        with self._memory_lock:
            return self._memory.checkpoint()

    def completed_interaction_candidate(
        self,
        interaction: CompletedConversationInteraction,
    ) -> EpisodicMemoryCandidate | None:
        with self._memory_lock:
            return self._memory.completed_interaction_candidate(interaction)

    def commit_completed_interaction(
        self,
        interaction: CompletedConversationInteraction,
    ) -> StateCommitReceipt | None:
        with self._memory_lock:
            return self._memory.commit_completed_interaction(interaction)

    def restore_memory_checkpoint(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.restore(checkpoint)

    def validate_memory_checkpoint(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.validate_checkpoint(checkpoint)

    def record_completed_reply(
        self, **values
    ) -> CompletedConversationInteraction | None:
        return self._conversations.record_completed_reply(**values)

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

    def selfhood(self, captured_at: UTCDateTime) -> SelfhoodSnapshot:
        return self._selfhood.snapshot().model_copy(update={"captured_at": captured_at})

    def selfhood_snapshot(self) -> SelfhoodSnapshot:
        return self._selfhood.snapshot()

    def selfhood_checkpoint(self):
        return self._selfhood.checkpoint()

    def validate_selfhood_checkpoint(self, checkpoint) -> None:
        self._selfhood.validate_checkpoint(checkpoint)

    def restore_selfhood_checkpoint(self, checkpoint) -> None:
        self._selfhood.restore(checkpoint)

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

    def profile_anchors(self, captured_at: UTCDateTime) -> ProfileAnchorSnapshot:
        return self._profile_anchors.model_copy(update={"captured_at": captured_at})


__all__ = ("BrainContextProvider", "CapabilityReader")
