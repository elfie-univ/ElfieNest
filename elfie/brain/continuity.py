"""Checkpoint contract for the continuous Emotion/Energy/Memory state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from elfie.brain.context_types import MemoryStateSnapshot
from elfie.brain.emotion.emotion_system import EmotionCheckpoint
from elfie.brain.energy.energy import EnergyCheckpoint
from elfie.brain.motivation import MotivationCheckpoint
from elfie.brain.offline_cognition import OfflineCognitionCheckpoint
from elfie.brain.state_lifecycle import StateCheckpoint


@dataclass(frozen=True)
class BrainContinuityCheckpoint:
    """One coherent checkpoint for the Stage 4C continuous state owners.

    Memory's checkpoint contains semantic revision/count metadata; the actual
    nodes remain owned by the injected durable ``MemoryStorePort``.
    """

    captured_at: datetime
    emotion: EmotionCheckpoint
    energy: EnergyCheckpoint
    memory: StateCheckpoint[MemoryStateSnapshot]
    motivation: MotivationCheckpoint
    offline_cognition: OfflineCognitionCheckpoint


__all__ = ("BrainContinuityCheckpoint",)
