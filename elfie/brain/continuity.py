"""Checkpoint contract for Brain's continuous state owners."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from elfie.brain.consolidation.system import CognitiveConsolidationCheckpoint
from elfie.brain.energy.energy import EnergyCheckpoint
from elfie.brain.memory.contracts import MemoryStateSnapshot
from elfie.brain.motivation.system import MotivationCheckpoint

# Import the Orientation package before context_types.  OrientationSystem's
# module imports EffectiveCapabilities from context_types; preloading the
# package preserves the existing package-initialization order without making
# Orientation part of this durable checkpoint.
from elfie.brain.orientation.contracts import (
    OrientationSnapshot as _OrientationSnapshot,  # noqa: F401
)
from elfie.brain.reasoning.context_types import ConversationContextCheckpoint
from elfie.brain.state_lifecycle import StateCheckpoint


@dataclass(frozen=True)
class BrainContinuityCheckpoint:
    """One coherent checkpoint for the Stage 4C continuous state owners.

    Memory's checkpoint contains semantic revision/count metadata; the actual
    nodes remain owned by the injected durable ``MemoryStorePort``.
    """

    captured_at: datetime
    energy: EnergyCheckpoint
    memory: StateCheckpoint[MemoryStateSnapshot]
    motivation: MotivationCheckpoint
    consolidation: CognitiveConsolidationCheckpoint
    conversation: ConversationContextCheckpoint = field(
        default_factory=ConversationContextCheckpoint
    )


__all__ = ("BrainContinuityCheckpoint",)
