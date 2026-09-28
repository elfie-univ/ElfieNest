"""Reasoning-owned bridge to one revision-pinned persistent Memory view."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from time import perf_counter
from typing import Literal, Protocol, Tuple
from uuid import uuid4

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
    RecallSense,
)
from elfie.brain.observation import (
    BrainObservation,
    BrainObservationSink,
    ObservationStatus,
)
from elfie.brain.reasoning.observation_payloads import (
    MemoryRecallBundleObservation,
    MemoryRecallRequestObservation,
    MemoryRecallResultObservation,
    MemoryRecallStarted,
    MemoryStateObservation,
    MemoryTurnOpened,
)
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import EventId, UTCDateTime

MemoryRecallStatus = Literal[
    "recalled",
    "skipped",
    "duplicate",
    "stale",
    "unavailable",
    "budget_exhausted",
]

_RECALL_COMPLETED_STATUSES = frozenset({"recalled", "skipped"})
_RECALL_SKIPPED_STATUSES = frozenset({"duplicate", "budget_exhausted"})


def _has_recall_input(request: RecallRequest) -> bool:
    return bool(
        request.text.strip()
        or request.seed_node_ids
        or request.sense is not None
        or request.kinship is not None
    )


def _request_cache_key(request: RecallRequest) -> RecallRequest:
    """Normalize only Query whitespace/case; retain every typed filter."""
    return replace(
        request,
        text=" ".join(request.text.casefold().split()),
        recall_id=None,
    )


def _initial_sense_request(emotion: EmotionSnapshot) -> RecallRequest | None:
    """Use only the strongest active canonical emotion from a current snapshot."""
    if emotion.freshness != "current" or not emotion.active:
        return None
    strongest = max(
        emotion.active,
        key=lambda item: (item.intensity, item.name.value),
    )
    return ReasoningMemoryBridge._request(
        sense=RecallSense(
            emotion_label=strongest.name.value,
            intensity=strongest.intensity,
        ),
        episode_limit=1,
    )


def _recall_observation_status(status: str) -> ObservationStatus:
    """Map one Memory recall status onto the envelope lifecycle state.

    Unified envelope rule: a gate-refused baseline ("not relevant" /
    "not requested") is a completed gate decision whose polarity lives in
    the payload, while a duplicate short-circuit or exhausted on-demand
    budget preempted the recall before its main effect (skipped).
    """
    if status in _RECALL_COMPLETED_STATUSES:
        return ObservationStatus.completed
    if status in _RECALL_SKIPPED_STATUSES:
        return ObservationStatus.skipped
    return ObservationStatus.degraded


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

    def recall(self, request: RecallRequest) -> MemoryRecallResult: ...


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
        self._results: OrderedDict[RecallRequest, MemoryRecallResult] = OrderedDict()
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

    def set_baseline(
        self, result: MemoryRecallResult, request: RecallRequest | None = None
    ) -> None:
        """Bind the single baseline result before the Run becomes visible."""
        with self._lock:
            self._baseline_result = result
            if request is not None:
                self._results[_request_cache_key(request)] = result

    def recall(self, request: RecallRequest) -> MemoryRecallResult:
        """Perform at most one unique on-demand Recall for P0."""
        if not _has_recall_input(request):
            result = MemoryRecallResult(
                status="unavailable",
                query=request.text,
                pinned_revision=self._pinned_revision,
                reason="empty_recall_request",
            )
            self._bridge._emit_recall_result(
                frame_id=self._frame_id,
                result=result,
                duration_ms=0.0,
            )
            return result
        with self._lock:
            cache_key = _request_cache_key(request)
            previous = self._results.get(cache_key)
            if previous is not None:
                result = MemoryRecallResult(
                    status="duplicate",
                    query=request.text,
                    pinned_revision=self._pinned_revision,
                    bundle=previous.bundle,
                    reason="query_already_recalled_in_run",
                )
                self._bridge._emit_recall_result(
                    frame_id=self._frame_id,
                    result=result,
                    duration_ms=0.0,
                )
                return result
            if self._on_demand_recalls >= self._max_on_demand_recalls:
                result = MemoryRecallResult(
                    status="budget_exhausted",
                    query=request.text,
                    pinned_revision=self._pinned_revision,
                    reason="on_demand_recall_budget_exhausted",
                )
                self._bridge._emit_recall_result(
                    frame_id=self._frame_id,
                    result=result,
                    duration_ms=0.0,
                )
                return result
            self._on_demand_recalls += 1
        result = self._bridge._recall_at_revision(  # noqa: SLF001 - owned session
            request,
            pinned_revision=self._pinned_revision,
            frame_id=self._frame_id,
        )
        with self._lock:
            self._results[cache_key] = result
        if result.bundle is not None:
            self._bridge.remember_additional_bundle(self._frame_id, result.bundle)
        return result


class ReasoningMemoryBridge:
    """Translate a Turn into pinned Recall without owning persistent facts."""

    def __init__(
        self,
        memory: MemorySystem,
        observation_sink: BrainObservationSink | None = None,
    ) -> None:
        self._memory = memory
        self._sink = observation_sink
        self._memory_lock = RLock()
        self._bundle_lock = RLock()
        self._emit_lock = RLock()
        self._emit_sequence = 0
        self._bundles: OrderedDict[str, RecallBundle] = OrderedDict()
        self._bundle_capacity = 256

    def open_turn(
        self,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        captured_at: UTCDateTime,
    ) -> ReasoningMemoryTurn:
        """Pin one revision, gate baseline Recall, and return the Run session."""
        # First-stage Recall is deliberately Sense-only. The owner message is
        # left for the model to interpret; Memory never guesses its intent.
        query = ""
        sink = self._sink
        pin_started = perf_counter() if sink is not None else 0.0
        try:
            with self._memory_lock:
                pinned_revision = self._memory.revision
                state = self._memory.snapshot(captured_at)
        except Exception:  # noqa: BLE001 - Memory boundary degrades explicitly
            pinned_revision = 0
            state = MemoryStateSnapshot.unknown().model_copy(
                update={"captured_at": captured_at}
            )
        pin_duration_ms = (
            round((perf_counter() - pin_started) * 1000.0, 2)
            if sink is not None
            else 0.0
        )
        self._emit_turn_opened(
            frame=frame,
            query=query,
            pinned_revision=pinned_revision,
            state=state,
            duration_ms=pin_duration_ms,
        )
        session = ReasoningMemorySession(
            self,
            frame_id=frame.frame_id,
            pinned_revision=pinned_revision,
        )
        baseline_request = _initial_sense_request(emotion)
        if baseline_request is not None:
            baseline = self._recall_at_revision(
                baseline_request,
                pinned_revision=pinned_revision,
                frame_id=frame.frame_id,
            )
        else:
            baseline = MemoryRecallResult(
                status="skipped",
                query=query,
                pinned_revision=pinned_revision,
                bundle=RecallBundle(recall_revision=pinned_revision),
                reason="baseline_recall_not_requested",
            )
            self._emit_recall_result(
                frame_id=frame.frame_id,
                result=baseline,
                duration_ms=0.0,
            )
        session.set_baseline(baseline, request=baseline_request)
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

    def _recall_at_revision(
        self,
        request: RecallRequest,
        *,
        pinned_revision: int,
        frame_id: EventId | None = None,
    ) -> MemoryRecallResult:
        recall_id = f"reasoning-recall:{uuid4().hex}"
        request = replace(request, recall_id=recall_id)
        self._emit_recall_started(
            recall_id=recall_id,
            frame_id=frame_id,
            query=request.text,
            pinned_revision=pinned_revision,
            request=request,
        )
        sink = self._sink
        recall_started = perf_counter() if sink is not None else 0.0

        def recall_elapsed_ms() -> float:
            """Zero-cost when unwired: perf_counter only runs with a sink."""
            return (
                round((perf_counter() - recall_started) * 1000.0, 2)
                if sink is not None
                else 0.0
            )

        try:
            with self._memory_lock:
                if self._memory.revision != pinned_revision:
                    result = MemoryRecallResult(
                        status="stale",
                        query=request.text,
                        pinned_revision=pinned_revision,
                        reason="memory_revision_changed_before_recall",
                    )
                    self._emit_recall_result(
                        recall_id=recall_id,
                        frame_id=frame_id,
                        result=result,
                        duration_ms=recall_elapsed_ms(),
                    )
                    return result
                bundle = self._memory.recall(request)
                if (
                    bundle.recall_revision != pinned_revision
                    or self._memory.revision != pinned_revision
                ):
                    result = MemoryRecallResult(
                        status="stale",
                        query=request.text,
                        pinned_revision=pinned_revision,
                        reason="memory_revision_changed_during_recall",
                    )
                    self._emit_recall_result(
                        recall_id=recall_id,
                        frame_id=frame_id,
                        result=result,
                        duration_ms=recall_elapsed_ms(),
                    )
                    return result
        except Exception as error:  # noqa: BLE001 - typed degradation boundary
            result = MemoryRecallResult(
                status="unavailable",
                query=request.text,
                pinned_revision=pinned_revision,
                reason=f"memory_unavailable:{type(error).__name__}",
            )
            self._emit_recall_result(
                recall_id=recall_id,
                frame_id=frame_id,
                result=result,
                duration_ms=recall_elapsed_ms(),
            )
            return result
        result = MemoryRecallResult(
            status="recalled",
            query=request.text,
            pinned_revision=pinned_revision,
            bundle=bundle,
        )
        self._emit_recall_result(
            recall_id=recall_id,
            frame_id=frame_id,
            result=result,
            duration_ms=recall_elapsed_ms(),
        )
        return result

    def _next_sequence(self) -> int:
        with self._emit_lock:
            self._emit_sequence += 1
            return self._emit_sequence

    def _emit_turn_opened(
        self,
        *,
        frame: TurnFrame,
        query: str,
        pinned_revision: int,
        state: MemoryStateSnapshot,
        duration_ms: float,
    ) -> None:
        sink = self._sink
        if sink is None:
            return
        frame_id = str(frame.frame_id)
        sink.emit(
            BrainObservation[MemoryTurnOpened](
                boundary="reasoning.memory_bridge",
                kind="turn_opened",
                sequence=self._next_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id="",
                frame_id=frame_id,
                cause_event_ids=tuple(str(item.meta.event_id) for item in frame.events),
                duration_ms=duration_ms,
                status=ObservationStatus.completed,
                payload=MemoryTurnOpened(
                    frame_id=frame_id,
                    query=query,
                    pinned_revision=pinned_revision,
                    state=MemoryStateObservation(
                        revision=state.revision,
                        episodic_count=state.episodic_count,
                        total_count=state.total_count,
                        snapshot_freshness=state.snapshot_freshness,
                    ),
                ),
            )
        )

    def _emit_recall_started(
        self,
        *,
        recall_id: str,
        frame_id: EventId | None,
        query: str,
        pinned_revision: int,
        request: RecallRequest,
    ) -> None:
        sink = self._sink
        if sink is None:
            return
        rendered_frame_id = str(frame_id) if frame_id is not None else None
        sink.emit(
            BrainObservation[MemoryRecallStarted](
                boundary="reasoning.memory_bridge",
                kind="recall_started",
                sequence=self._next_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id="",
                frame_id=rendered_frame_id or "",
                cause_event_ids=(),
                duration_ms=0.0,
                status=ObservationStatus.completed,
                payload=MemoryRecallStarted(
                    recall_id=recall_id,
                    frame_id=rendered_frame_id,
                    query=query,
                    pinned_revision=pinned_revision,
                    request=MemoryRecallRequestObservation(
                        has_query=bool(request.text.strip()),
                        sense_emotion=(
                            request.sense.emotion_label
                            if request.sense is not None
                            else None
                        ),
                        kinship_relation=(
                            request.kinship.relation
                            if request.kinship is not None
                            else None
                        ),
                        record_kinds=request.record_kinds,
                        has_filters=bool(
                            request.node_types
                            or request.relation_types
                            or request.occurred_from
                            or request.occurred_to
                            or request.minimum_importance is not None
                            or request.person_node_ids
                            or request.place_node_ids
                            or request.emotion_labels
                            or request.topic_labels
                            or request.cause_labels
                        ),
                        seed_limit=request.seed_limit,
                        node_limit=request.node_limit,
                        assertion_limit=request.assertion_limit,
                        episode_limit=request.episode_limit,
                        evidence_limit=request.evidence_limit,
                        character_limit=request.character_limit,
                    ),
                ),
            )
        )

    def _emit_recall_result(
        self,
        *,
        recall_id: str | None = None,
        frame_id: EventId | None,
        result: MemoryRecallResult,
        duration_ms: float,
    ) -> None:
        sink = self._sink
        if sink is None:
            return
        resolved_recall_id = recall_id or f"reasoning-recall:{uuid4().hex}"
        rendered_frame_id = str(frame_id) if frame_id is not None else None
        bundle = result.bundle
        sink.emit(
            BrainObservation[MemoryRecallResultObservation](
                boundary="reasoning.memory_bridge",
                kind="recall_result",
                sequence=self._next_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id="",
                frame_id=rendered_frame_id or "",
                cause_event_ids=(),
                duration_ms=duration_ms,
                status=_recall_observation_status(result.status),
                payload=MemoryRecallResultObservation(
                    recall_id=resolved_recall_id,
                    frame_id=rendered_frame_id,
                    query=result.query,
                    status=result.status,
                    pinned_revision=result.pinned_revision,
                    reason=result.reason,
                    bundle=(
                        MemoryRecallBundleObservation(
                            recall_revision=bundle.recall_revision,
                            focus_node_ids=tuple(
                                item.node_id for item in bundle.focus_nodes
                            ),
                            assertion_ids=tuple(
                                item.assertion_id for item in bundle.assertions
                            ),
                            episode_ids=tuple(
                                item.episode_id for item in bundle.episodes
                            ),
                            evidence_ids=tuple(
                                item.evidence_id for item in bundle.evidence
                            ),
                            path_count=len(bundle.paths),
                            conflict_count=len(bundle.conflicts),
                        )
                        if bundle is not None
                        else None
                    ),
                ),
            )
        )

    @staticmethod
    def _request(
        *,
        text: str = "",
        sense: RecallSense | None = None,
        episode_limit: int = 8,
    ) -> RecallRequest:
        return RecallRequest(
            text=text,
            sense=sense,
            seed_limit=8,
            node_limit=32,
            assertion_limit=48,
            episode_limit=episode_limit,
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
