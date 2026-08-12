"""Narrow typed dependencies consumed by BrainCoordinator."""

from typing import Optional, Protocol

from elfie.brain.context_types import (
    ActivityContext,
    ConversationContext,
    EffectiveCapabilities,
    EmotionSnapshot,
    MemoryContext,
    MotivationSnapshot,
    OfflineCognitionSnapshot,
    OrientationSnapshot,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)
from elfie.brain.decision_types import TurnDecision
from elfie.brain.motivation import RecoveryDriveCandidate
from elfie.brain.offline_cognition import OfflineCognitionCandidate
from elfie.brain.perception_types import TurnFrame
from elfie.message_types import TurnId, UTCDateTime


class BrainContextSource(Protocol):
    """Coordinator-owned reads for history, memory, and capabilities."""

    def conversation(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        """Return bounded conversation history for the frame."""

    def memory(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> MemoryContext:
        """Return memory excerpts selected by the Brain owner."""

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

    def selfhood(self, captured_at: UTCDateTime) -> SelfhoodSnapshot:
        """Return the committed mutable self-model at the Turn cutoff."""

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

    def offline_cognition(self, captured_at: UTCDateTime) -> OfflineCognitionSnapshot:
        """Return quiet-window memory整理 state at the Turn cutoff."""

    def evaluate_offline_cognition(
        self,
        *,
        sleeping: bool,
        now: UTCDateTime,
        blocked: bool,
    ) -> Optional[OfflineCognitionCandidate]:
        """Evaluate one bounded quiet-window consolidation candidate."""

    def profile_anchors(self, captured_at: UTCDateTime) -> ProfileAnchorSnapshot:
        """Return immutable identity and appearance anchors at the Turn cutoff."""


class TurnDecisionSink(Protocol):
    """Atomic governed-decision boundary implemented by OutputRouter."""

    def accept(self, decision: TurnDecision) -> bool:
        """Accept the scoped decision before its frame is committed."""

    def cancel_stale(self, turn_id: TurnId, reason: str) -> None:
        """Cancel not-yet-started work for a stale turn."""


__all__ = ("BrainContextSource", "TurnDecisionSink")
