"""Single commit boundary for state candidates produced by one Turn."""

from __future__ import annotations

from typing import Callable, Protocol, Tuple, Union

from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCommitReceipt,
    StateCommitStatus,
)

TurnStateCandidate = Union[
    EpisodicMemoryCandidate,
    StateCandidate[OrientationSnapshot],
]


class TurnSettlementPort(Protocol):
    """Commit validated owner candidates without executing external directives."""

    def settle(
        self,
        candidates: Tuple[TurnStateCandidate, ...],
    ) -> Tuple[StateCommitReceipt, ...]:
        """Commit each candidate through its authoritative owner."""


class TurnSettlement:
    """Route explicit candidates to Memory or Orientation's sole owner."""

    def __init__(
        self,
        memory: MemorySystem,
        *,
        orientation: Callable[[StateCandidate[OrientationSnapshot]], StateCommitReceipt]
        | None = None,
    ) -> None:
        self._memory = memory
        self._orientation = orientation

    def settle(
        self,
        candidates: Tuple[TurnStateCandidate, ...],
    ) -> Tuple[StateCommitReceipt, ...]:
        receipts = tuple(self._commit(candidate) for candidate in candidates)
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
            raise RuntimeError(f"Turn state settlement failed: {reasons}")
        return receipts

    def _commit(self, candidate: TurnStateCandidate) -> StateCommitReceipt:
        if isinstance(candidate, EpisodicMemoryCandidate):
            return self._memory.commit_episode_candidate(candidate)
        if candidate.owner == "orientation" and self._orientation is not None:
            return self._orientation(candidate)
        raise RuntimeError(f"Turn state owner is unavailable: {candidate.owner}")


__all__ = (
    "TurnSettlement",
    "TurnSettlementPort",
    "TurnStateCandidate",
)
