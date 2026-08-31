"""Read-only Memory retrieval and explicit candidate preparation."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Tuple

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import MemoryContext, RelationshipImportanceProjection
from elfie.brain.memory.memory_records import (
    MemoryUseProposal,
    RecallBundle,
    RecallRequest,
)
from elfie.brain.reasoning.context_types import CompletedConversationInteraction
from elfie.brain.state_lifecycle import StateCommitReceipt, StateCommitStatus
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import EventId, UTCDateTime


class MemoryContextReader:
    """Translate a Turn into recall results without writing the Memory owner."""

    def __init__(self, memory: MemorySystem) -> None:
        self._memory = memory
        self._bundle_lock = RLock()
        self._bundles: OrderedDict[str, RecallBundle] = OrderedDict()
        self._bundle_capacity = 256

    def read(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        query_parts: list[str] = []
        del emotion
        for event in frame.events:
            if isinstance(event.payload, SocialPayload):
                query_parts.append(event.payload.content)
        state = self._memory.snapshot(captured_at)
        if not query_parts:
            bundle = RecallBundle(recall_revision=self._memory.revision)
            self._remember_bundle(frame.frame_id, bundle)
            return MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                state=state,
                recall_revision=bundle.recall_revision,
            )
        query = "\n".join(query_parts)
        bundle = self._memory.recall(
            RecallRequest(
                text=query,
                mode="basic_local",
                seed_limit=8,
                node_limit=32,
                assertion_limit=48,
                episode_limit=8,
                evidence_limit=16,
                character_limit=6000,
            )
        )
        self._remember_bundle(frame.frame_id, bundle)
        return MemoryContext(
            revision=frame.revision,
            captured_at=captured_at,
            recall=bundle,
            state=state,
            recall_revision=bundle.recall_revision,
        )

    def submit_use_proposal(
        self, frame_id: EventId, proposal: MemoryUseProposal
    ) -> bool:
        """Submit model-selected IDs against the exact frame RecallBundle."""
        with self._bundle_lock:
            bundle = self._bundles.get(str(frame_id))
        if bundle is None:
            raise ValueError("memory RecallBundle for frame is no longer available")
        return self._memory.submit_memory_use_proposal(proposal, bundle)

    def _remember_bundle(self, frame_id: EventId, bundle: RecallBundle) -> None:
        """Keep only a bounded frame→bundle binding for settlement."""
        key = str(frame_id)
        with self._bundle_lock:
            self._bundles.pop(key, None)
            self._bundles[key] = bundle
            while len(self._bundles) > self._bundle_capacity:
                self._bundles.popitem(last=False)

    def candidates(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> Tuple[EpisodicMemoryCandidate, ...]:
        """Do not persist an owner-only half interaction.

        Durable interaction candidates are prepared only after a completed
        communication receipt joins the owner's input to Elfie's actual reply.
        """
        del frame, emotion, captured_at
        return ()

    def relationship_importance(
        self,
        actor_id: str,
        *,
        owner: bool = False,
    ) -> RelationshipImportanceProjection | None:
        return self._memory.relationship_importance(actor_id, owner=owner)

    def completed_interaction_candidate(
        self,
        interaction: CompletedConversationInteraction,
    ) -> EpisodicMemoryCandidate | None:
        """Prepare one source-grounded episode for a completed interaction.

        The source participant is retained verbatim; only owner messages get
        the legacy human-readable wording used by existing diagnostics.  The
        receipt proves that both sides of the interaction exist, so source
        capture must not depend on a magic word in the owner's message.  Any
        later promotion to a durable claim is the consolidation stage's
        responsibility.
        """
        if interaction.owner.sender.source_kind == "owner":
            incoming = f"主人对我说: '{interaction.owner.content}'"
            outgoing = f"我回复主人: '{interaction.reply.content}'"
        else:
            incoming = (
                f"{interaction.owner.sender.source_kind}"
                f"({interaction.owner.sender.actor_id})对我说: '{interaction.owner.content}'"
            )
            outgoing = f"我回复对方: '{interaction.reply.content}'"
        return EpisodicMemoryCandidate(
            candidate_id=EventId(f"memory-interaction:{interaction.receipt_id}"),
            base_revision=self._memory.revision,
            content=(f"{incoming}。\n{outgoing}。\n投递结果: completed。"),
            emotion="calm",
            intensity=0.0,
            stimulus=f"completed-owner-interaction:{interaction.conversation_id}",
            source_event_ids=(
                interaction.owner.event_id,
                interaction.reply.event_id,
                interaction.receipt_id,
            ),
            created_at=interaction.reply.occurred_at,
        )

    def commit_completed_interaction(
        self,
        interaction: CompletedConversationInteraction,
    ) -> StateCommitReceipt | None:
        """Commit one receipt-backed source episode with one bounded stale retry."""
        candidate = self.completed_interaction_candidate(interaction)
        if candidate is None:
            return None
        receipt = self._memory.commit_episode_candidate(candidate)
        if receipt.status is StateCommitStatus.STALE:
            candidate = candidate.model_copy(
                update={"base_revision": self._memory.revision}
            )
            receipt = self._memory.commit_episode_candidate(candidate)
        return receipt

    def checkpoint(self):
        return self._memory.checkpoint()

    def validate_checkpoint(self, checkpoint) -> None:
        self._memory.validate_checkpoint(checkpoint)

    def restore(self, checkpoint) -> None:
        self._memory.restore(checkpoint)


__all__ = ("MemoryContextReader",)
