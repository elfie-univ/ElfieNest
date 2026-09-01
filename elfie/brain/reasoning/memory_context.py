"""Reasoning-owned bridge to one revision-pinned persistent Memory view."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Literal, Protocol, Tuple

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.memory import EpisodicMemoryCandidate, MemorySystem
from elfie.brain.memory.contracts import (
    MemoryContext,
    MemoryStateSnapshot,
    RelationshipImportanceProjection,
)
from elfie.brain.memory.memory_records import (
    MemoryUseProposal,
    RecallBundle,
    RecallRequest,
)
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import EventId, UTCDateTime

MemoryRecallStatus = Literal[
    "recalled",
    "skipped",
    "duplicate",
    "stale",
    "unavailable",
    "budget_exhausted",
]

_RECALL_INTENT = re.compile(
    r"(?:记得|之前|上次|以前|历史|回忆|偏好|喜欢|不喜欢|习惯|"
    r"纠正|更正|其实|冲突|矛盾|那个|这件事|这回事|他(?:说|是)|"
    r"她(?:说|是)|它(?:是|呢)|来自哪里|认识|我们.{0,12}(?:说过|聊过)|"
    r"remember|previous(?:ly)?|last\s+time|history|prefer|like|dislike|"
    r"correct|conflict|that\s+(?:one|thing)|who\s+is)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryRecallResult:
    """One explicit baseline or on-demand Recall outcome."""

    status: MemoryRecallStatus
    query: str
    pinned_revision: int
    bundle: RecallBundle | None = None
    reason: str | None = None


class MemoryRecallSessionPort(Protocol):
    """The bounded same-Run Recall capability consumed by the Agent Loop."""

    @property
    def pinned_revision(self) -> int: ...

    @property
    def baseline_result(self) -> MemoryRecallResult: ...

    def recall(self, query: str) -> MemoryRecallResult: ...


@dataclass(frozen=True)
class ReasoningMemoryTurn:
    """Memory context plus the only on-demand Recall session for one Run."""

    context: MemoryContext
    session: MemoryRecallSessionPort


class ReasoningMemorySession:
    """Deduplicate and bound on-demand Recall against one pinned revision."""

    def __init__(
        self,
        bridge: ReasoningMemoryBridge,
        *,
        frame_id: EventId,
        pinned_revision: int,
        max_on_demand_recalls: int = 1,
    ) -> None:
        self._bridge = bridge
        self._frame_id = frame_id
        self._pinned_revision = pinned_revision
        self._max_on_demand_recalls = max_on_demand_recalls
        self._on_demand_recalls = 0
        self._results: OrderedDict[str, MemoryRecallResult] = OrderedDict()
        self._lock = RLock()
        self._baseline_result = MemoryRecallResult(
            status="skipped",
            query="",
            pinned_revision=pinned_revision,
            bundle=RecallBundle(recall_revision=pinned_revision),
            reason="baseline_recall_not_requested",
        )

    @property
    def pinned_revision(self) -> int:
        return self._pinned_revision

    @property
    def baseline_result(self) -> MemoryRecallResult:
        return self._baseline_result

    def set_baseline(self, result: MemoryRecallResult) -> None:
        """Bind the single baseline result before the Run becomes visible."""
        with self._lock:
            self._baseline_result = result
            normalized = self._normalize(result.query)
            if normalized:
                self._results[normalized] = result

    def recall(self, query: str) -> MemoryRecallResult:
        """Perform at most one unique on-demand Recall for P0."""
        normalized = self._normalize(query)
        if not normalized:
            return MemoryRecallResult(
                status="unavailable",
                query=query,
                pinned_revision=self._pinned_revision,
                reason="blank_recall_query",
            )
        with self._lock:
            previous = self._results.get(normalized)
            if previous is not None:
                return MemoryRecallResult(
                    status="duplicate",
                    query=query,
                    pinned_revision=self._pinned_revision,
                    bundle=previous.bundle,
                    reason="query_already_recalled_in_run",
                )
            if self._on_demand_recalls >= self._max_on_demand_recalls:
                return MemoryRecallResult(
                    status="budget_exhausted",
                    query=query,
                    pinned_revision=self._pinned_revision,
                    reason="on_demand_recall_budget_exhausted",
                )
            self._on_demand_recalls += 1
        result = self._bridge._recall_at_revision(  # noqa: SLF001 - owned session
            query,
            pinned_revision=self._pinned_revision,
        )
        with self._lock:
            self._results[normalized] = result
        if result.bundle is not None:
            self._bridge.remember_additional_bundle(self._frame_id, result.bundle)
        return result

    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join(query.casefold().split())


class ReasoningMemoryBridge:
    """Translate a Turn into pinned Recall without owning persistent facts."""

    def __init__(self, memory: MemorySystem) -> None:
        self._memory = memory
        self._memory_lock = RLock()
        self._bundle_lock = RLock()
        self._bundles: OrderedDict[str, RecallBundle] = OrderedDict()
        self._bundle_capacity = 256

    def open_turn(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> ReasoningMemoryTurn:
        """Pin one revision, gate baseline Recall, and return the Run session."""
        del emotion
        query = "\n".join(
            event.payload.content
            for event in frame.events
            if isinstance(event.payload, SocialPayload)
        ).strip()
        try:
            with self._memory_lock:
                pinned_revision = self._memory.revision
                state = self._memory.snapshot(captured_at)
        except Exception:  # noqa: BLE001 - Memory boundary degrades explicitly
            pinned_revision = 0
            state = MemoryStateSnapshot.unknown().model_copy(
                update={"captured_at": captured_at}
            )
        session = ReasoningMemorySession(
            self,
            frame_id=frame.frame_id,
            pinned_revision=pinned_revision,
        )
        if query and self.should_recall(query):
            baseline = self._recall_at_revision(
                query,
                pinned_revision=pinned_revision,
            )
        else:
            baseline = MemoryRecallResult(
                status="skipped",
                query=query,
                pinned_revision=pinned_revision,
                bundle=RecallBundle(recall_revision=pinned_revision),
                reason="baseline_recall_not_relevant",
            )
        session.set_baseline(baseline)
        bundle = baseline.bundle or RecallBundle(recall_revision=pinned_revision)
        self._remember_bundle(frame.frame_id, bundle)
        return ReasoningMemoryTurn(
            context=MemoryContext(
                revision=frame.revision,
                captured_at=captured_at,
                recall=bundle,
                state=state,
                recall_revision=pinned_revision,
            ),
            session=session,
        )

    @staticmethod
    def should_recall(query: str) -> bool:
        """Skip greetings/small talk that carry no historical retrieval intent."""
        return _RECALL_INTENT.search(query) is not None

    def _recall_at_revision(
        self,
        query: str,
        *,
        pinned_revision: int,
    ) -> MemoryRecallResult:
        try:
            with self._memory_lock:
                if self._memory.revision != pinned_revision:
                    return MemoryRecallResult(
                        status="stale",
                        query=query,
                        pinned_revision=pinned_revision,
                        reason="memory_revision_changed_before_recall",
                    )
                bundle = self._memory.recall(self._request(query))
                if (
                    bundle.recall_revision != pinned_revision
                    or self._memory.revision != pinned_revision
                ):
                    return MemoryRecallResult(
                        status="stale",
                        query=query,
                        pinned_revision=pinned_revision,
                        reason="memory_revision_changed_during_recall",
                    )
        except Exception as error:  # noqa: BLE001 - typed degradation boundary
            return MemoryRecallResult(
                status="unavailable",
                query=query,
                pinned_revision=pinned_revision,
                reason=f"memory_unavailable:{type(error).__name__}",
            )
        return MemoryRecallResult(
            status="recalled",
            query=query,
            pinned_revision=pinned_revision,
            bundle=bundle,
        )

    @staticmethod
    def _request(query: str) -> RecallRequest:
        return RecallRequest(
            text=query,
            mode="basic_local",
            seed_limit=8,
            node_limit=32,
            assertion_limit=48,
            episode_limit=8,
            evidence_limit=16,
            character_limit=6000,
        )

    def submit_use_proposal(
        self, frame_id: EventId, proposal: MemoryUseProposal
    ) -> bool:
        """Submit model-selected IDs against the exact frame RecallBundle."""
        with self._bundle_lock:
            bundle = self._bundles.get(str(frame_id))
        if bundle is None:
            raise ValueError("memory RecallBundle for frame is no longer available")
        with self._memory_lock:
            return self._memory.submit_memory_use_proposal(proposal, bundle)

    def _remember_bundle(self, frame_id: EventId, bundle: RecallBundle) -> None:
        key = str(frame_id)
        with self._bundle_lock:
            self._bundles.pop(key, None)
            self._bundles[key] = bundle
            while len(self._bundles) > self._bundle_capacity:
                self._bundles.popitem(last=False)

    def remember_additional_bundle(
        self,
        frame_id: EventId,
        bundle: RecallBundle,
    ) -> None:
        """Merge same-revision on-demand IDs into the frame settlement allow-list."""
        with self._bundle_lock:
            existing = self._bundles.get(str(frame_id))
            if existing is None:
                raise ValueError("memory RecallBundle for frame is no longer available")
            if existing.recall_revision != bundle.recall_revision:
                raise ValueError("cannot mix RecallBundle revisions in one frame")
            merged = RecallBundle(
                focus_nodes=tuple(
                    {
                        item.node_id: item
                        for item in existing.focus_nodes + bundle.focus_nodes
                    }.values()
                ),
                assertions=tuple(
                    {
                        item.assertion_id: item
                        for item in existing.assertions + bundle.assertions
                    }.values()
                ),
                paths=tuple(dict.fromkeys(existing.paths + bundle.paths)),
                episodes=tuple(
                    {
                        item.episode_id: item
                        for item in existing.episodes + bundle.episodes
                    }.values()
                ),
                evidence=tuple(
                    {
                        item.evidence_id: item
                        for item in existing.evidence + bundle.evidence
                    }.values()
                ),
                conflicts=tuple(dict.fromkeys(existing.conflicts + bundle.conflicts)),
                recall_revision=existing.recall_revision,
                limits=bundle.limits,
            )
            self._bundles[str(frame_id)] = merged

    def candidates(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> Tuple[EpisodicMemoryCandidate, ...]:
        del frame, emotion, captured_at
        return ()

    def relationship_importance(
        self,
        actor_id: str,
        *,
        owner: bool = False,
    ) -> RelationshipImportanceProjection | None:
        with self._memory_lock:
            return self._memory.relationship_importance(actor_id, owner=owner)

    def checkpoint(self):
        with self._memory_lock:
            return self._memory.checkpoint()

    def validate_checkpoint(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.validate_checkpoint(checkpoint)

    def restore(self, checkpoint) -> None:
        with self._memory_lock:
            self._memory.restore(checkpoint)


__all__ = (
    "MemoryRecallResult",
    "MemoryRecallSessionPort",
    "MemoryRecallStatus",
    "ReasoningMemoryBridge",
    "ReasoningMemorySession",
    "ReasoningMemoryTurn",
)
