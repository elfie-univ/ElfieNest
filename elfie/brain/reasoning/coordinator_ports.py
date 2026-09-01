"""Narrow typed dependencies consumed by BrainCoordinator."""

from typing import Callable, Optional, Protocol

from elfie.brain.activity.context import ActivityContext
from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.consolidation.system import CognitiveConsolidationCandidate
from elfie.brain.emotion.contracts import EmotionSnapshot, TrustedAppraisalScope
from elfie.brain.memory import EpisodicMemoryCandidate
from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    MemoryUseProposal,
)
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.motivation.system import RecoveryDriveCandidate
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.context_types import (
    ConversationContext,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.decision_types import TurnDecision
from elfie.brain.reasoning.memory_context import ReasoningMemoryTurn
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.brain.state_lifecycle import StateCommitReceipt
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import TurnId, UTCDateTime


class BrainContextSource(Protocol):
    """Coordinator-owned reads for history, memory, and capabilities."""

    def conversation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        """Return bounded conversation history for the frame."""

    def memory_turn(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> ReasoningMemoryTurn:
        """Return pinned baseline Recall and the only same-Run Recall session."""

    def memory_candidates(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> tuple[EpisodicMemoryCandidate, ...]:
        """Return explicit candidates without mutating Memory."""

    def emotion_appraisal_scopes(
        self,
        frame: TurnFrame,
    ) -> tuple[TrustedAppraisalScope, ...]:
        """Return host-signed indirect scopes for source actors in this frame."""

    def flush_pending_handoffs(
        self,
        capture: Callable[[tuple[ClosedEpisode, ...]], tuple[StateCommitReceipt, ...]],
    ) -> tuple[StateCommitReceipt, ...]:
        """Run the only Context Workspace to persistent Memory handoff path."""

    def activities(self, captured_at: UTCDateTime) -> ActivityContext:
        """Return the bounded committed Activity projection at the Turn cutoff."""

    def capabilities(self, captured_at: UTCDateTime) -> EffectiveCapabilities:
        """Return current Body and connected-channel capabilities."""

    def orientation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
        turn_id: TurnId,
        capabilities: EffectiveCapabilities,
    ) -> OrientationSnapshot:
        """Observe the admitted frame and return current self/world placement."""

    def selfhood(self, captured_at: UTCDateTime) -> SelfhoodPromptProjection:
        """Return the deterministic model-facing projection at the cutoff."""

    def motivation(self, captured_at: UTCDateTime) -> MotivationSnapshot:
        """Return the committed fixed-drive state at the Turn cutoff."""

    def evaluate_motivation(
        self,
        *,
        energy: float,
        fatigue: float,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[RecoveryDriveCandidate]:
        """Evaluate the bounded fixed drive at a coordinator clock boundary."""

    def consolidation(self, captured_at: UTCDateTime) -> CognitiveConsolidationSnapshot:
        """Return quiet-window memory整理 state at the Turn cutoff."""

    def evaluate_consolidation(
        self,
        *,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[CognitiveConsolidationCandidate]:
        """Evaluate one bounded quiet-window consolidation candidate."""

    def submit_memory_use_proposal(
        self,
        frame_id: str,
        proposal: MemoryUseProposal,
    ) -> bool:
        """Record model-selected IDs against the frame's Recall snapshot."""


class TurnDecisionSink(Protocol):
    """Atomic governed-decision boundary implemented by OutputRouter."""

    def accept(self, decision: TurnDecision) -> bool:
        """Accept the scoped decision before its frame is committed."""

    def cancel_stale(self, turn_id: TurnId, reason: str) -> None:
        """Cancel not-yet-started work for a stale turn."""


__all__ = ("BrainContextSource", "TurnDecisionSink")
