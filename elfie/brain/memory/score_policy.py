"""The single versioned semantic score policy for Memory.

``importance`` and ``confidence`` are the only scores in the target Memory
contract.  Evidence reinforces those two values through this policy; no
parallel support or retention score is maintained.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

EvidenceStance = Literal["supports", "contradicts", "context"]


@dataclass(frozen=True)
class SemanticScoreUpdate:
    """The score changes caused by one distinct evidence contribution."""

    confidence: float
    importance: float


class MemoryScorePolicy:
    """Versioned, deterministic updates for sourced Memory facts."""

    version = "memory.v1"
    lifecycle_decay = 0.05
    forget_importance_threshold = 0.10

    @classmethod
    def evidence_update(
        cls,
        *,
        confidence: float,
        importance: float,
        stance: EvidenceStance,
        evidence_confidence: float = 1.0,
    ) -> SemanticScoreUpdate:
        """Return bounded scores after one *new* evidence link.

        Supporting evidence gradually reinforces both scores.  Contradicting
        evidence lowers confidence but preserves importance so a disputed fact
        remains discoverable.  Context evidence carries provenance only.
        Callers must ensure the evidence link is new before invoking this
        method; duplicate links are idempotent no-ops.
        """
        current_confidence = _bounded(confidence)
        current_importance = _bounded(importance)
        quality = _bounded(evidence_confidence)
        if stance == "supports":
            return SemanticScoreUpdate(
                confidence=_bounded(
                    current_confidence + (1.0 - current_confidence) * 0.20 * quality
                ),
                importance=_bounded(
                    current_importance + (1.0 - current_importance) * 0.05 * quality
                ),
            )
        if stance == "contradicts":
            return SemanticScoreUpdate(
                confidence=_bounded(current_confidence * (1.0 - 0.20 * quality)),
                importance=current_importance,
            )
        return SemanticScoreUpdate(
            confidence=current_confidence,
            importance=current_importance,
        )

    @staticmethod
    def next_review_at(captured_at: str, *, days: int = 7) -> str:
        """Return a deterministic UTC review deadline for reinforced facts."""
        current = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return (current + timedelta(days=max(1, days))).isoformat(
            timespec="milliseconds"
        )

    @classmethod
    def decay_importance(cls, importance: float) -> float:
        """Apply one due-review decay step without introducing another score."""
        return _bounded(float(importance) - cls.lifecycle_decay)

    @classmethod
    def can_forget(cls, importance: float) -> bool:
        """Return whether policy permits forgetting a dependency-safe source."""
        return _bounded(importance) <= cls.forget_importance_threshold


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


__all__ = ["EvidenceStance", "MemoryScorePolicy", "SemanticScoreUpdate"]
