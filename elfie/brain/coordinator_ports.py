"""Narrow typed dependencies consumed by BrainCoordinator."""

from typing import Protocol

from elfie.brain.context_types import (
    ConversationContext,
    EffectiveCapabilities,
    EmotionSnapshot,
    MemoryContext,
)
from elfie.brain.decision_types import TurnDecision
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

    def capabilities(self, captured_at: UTCDateTime) -> EffectiveCapabilities:
        """Return current Body and connected-channel capabilities."""


class TurnDecisionSink(Protocol):
    """Atomic governed-decision boundary implemented by OutputRouter."""

    def accept(self, decision: TurnDecision) -> bool:
        """Accept the scoped decision before its frame is committed."""

    def cancel_stale(self, turn_id: TurnId, reason: str) -> None:
        """Cancel not-yet-started work for a stale turn."""


__all__ = ("BrainContextSource", "TurnDecisionSink")
