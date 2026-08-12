"""Cognitive Consolidation: bounded offline state reorganization without effects."""

from .contracts import CognitiveConsolidationSnapshot
from .system import (
    CognitiveConsolidationCandidate,
    CognitiveConsolidationCheckpoint,
    CognitiveConsolidationRestoreError,
    CognitiveConsolidationResult,
    CognitiveConsolidationStatus,
    CognitiveConsolidationSystem,
    consolidation_candidate_to_perception,
)

__all__ = (
    "CognitiveConsolidationCandidate",
    "CognitiveConsolidationSnapshot",
    "CognitiveConsolidationCheckpoint",
    "CognitiveConsolidationRestoreError",
    "CognitiveConsolidationResult",
    "CognitiveConsolidationStatus",
    "CognitiveConsolidationSystem",
    "consolidation_candidate_to_perception",
)
