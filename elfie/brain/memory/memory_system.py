"""记忆系统门面：统一暴露 source-first Memory API。"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Dict, cast
from uuid import uuid4

from elfie.brain.memory.contracts import (
    MemoryStateSnapshot,
    RelationshipImportanceProjection,
)
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCheckpoint,
    StateCommitReceipt,
    StateCommitStatus,
    StateRestoreError,
    VersionedState,
    VersionedStateStore,
)
from elfie.message_types import EventId

from .candidates import EpisodicMemoryCandidate
from .consolidation import MemoryConsolidator
from .memory_records import (
    ClosedEpisode,
    ConsolidationBatchReceipt,
    ConsolidationRequest,
    EpisodeReceipt,
    MaintenanceReceipt,
    MaintenanceRequest,
    MemoryInspectionSnapshot,
    MemoryUseProposal,
    QualifiedReinforcementReceipt,
    RecallBundle,
    RecallRequest,
)
from .memory_store import MemoryStorePort
from .model_food import MemoryModelPort
from .recall_renderer import render_recall_bundle

logger = logging.getLogger("elfie.brain.memory.memory_system")


def _parse_timestamp(value: str) -> datetime:
    """Parse a typed event timestamp for proposal ordering checks."""
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class MemorySystem:
    """记忆系统门面：组合所有子系统，提供统一API"""

    def __init__(
        self,
        storage: MemoryStorePort,
        *,
        elfie_id: str | None = None,
        personality_data: dict | None = None,
        clock: Callable[[], datetime] | None = None,
        initial_at: datetime | None = None,
    ):
        """初始化 typed Memory 主线；具体存储由 Bootstrap 注入。"""
        self.storage = storage
        del personality_data
        if not all(
            callable(getattr(storage, name, None))
            for name in ("record_episode", "apply_consolidation", "recall")
        ):
            raise TypeError("MemorySystem requires the typed source-first Memory store")
        self._typed_memory = True
        if elfie_id is not None:
            binder = getattr(storage, "bind_elfie_identity", None)
            if callable(binder):
                binder(elfie_id)
        self._owns_storage = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        state_at = initial_at or self._clock()
        total_count = storage.count_memory_records()
        initial_state = MemoryStateSnapshot(
            revision=0,
            captured_at=state_at,
            episodic_count=storage.count_episodes(),
            total_count=total_count,
            snapshot_freshness="current" if total_count else "unknown",
        )
        self._state = VersionedStateStore(
            VersionedState(
                revision=0,
                committed_at=state_at,
                source_event_ids=(),
                causation_id=None,
                value=initial_state,
            )
        )
        self._episode_candidate_lock = RLock()
        # State candidates are built from a snapshot and then committed.  The
        # storage mutation that precedes that commit may run on the Brain
        # worker while a completed-turn settlement is committing another
        # mutation, so serialize the snapshot→commit window here as well.
        self._state_commit_lock = RLock()
        self._committed_episode_candidate_ids: set[EventId] = set()
        self._committed_episode_candidate_order: deque[EventId] = deque(maxlen=2048)
        self._use_proposals: dict[str, MemoryUseProposal] = {}
        self._use_proposal_order: deque[str] = deque(maxlen=2048)
        self.consolidator = MemoryConsolidator(self.storage, elfie_id=elfie_id)

    def bind_elfie_identity(
        self,
        elfie_id: str,
    ) -> None:
        binder = getattr(self.storage, "bind_elfie_identity", None)
        if callable(binder):
            binder(elfie_id)
        self.consolidator.elfie_id = elfie_id

    def relationship_importance(
        self,
        actor_id: str,
        *,
        owner: bool = False,
    ) -> RelationshipImportanceProjection | None:
        """Read one source actor's trusted relationship importance."""

        normalized_actor = actor_id.strip()
        if not normalized_actor:
            return None
        entities = tuple(
            node
            for node in self.storage.list_graph_nodes(limit=1000)
            if node.node_type == "entity"
        )
        exact = tuple(
            node
            for node in entities
            if normalized_actor
            in {
                node.node_id,
                str(node.properties.get("person_id") or "").strip(),
            }
        )
        candidates = exact
        if not candidates and owner:
            owners = tuple(
                node for node in entities if bool(node.properties.get("is_owner"))
            )
            candidates = owners if len(owners) == 1 else ()
        if len(candidates) != 1:
            return None
        raw_importance = candidates[0].properties.get("importance_score")
        if raw_importance is None:
            return None
        if isinstance(raw_importance, bool) or not isinstance(
            raw_importance, (int, float, str)
        ):
            return None
        try:
            importance = max(0.0, min(1.0, float(raw_importance)))
        except (TypeError, ValueError):
            return None
        return RelationshipImportanceProjection(
            actor_id=normalized_actor,
            revision=self.revision,
            importance=importance,
        )

    def record_closed_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        """Persist one already-closed Episode through the source-first contract."""
        recorder = getattr(self.storage, "record_episode", None)
        if not callable(recorder):
            raise TypeError("the configured Memory store does not support Episodes")
        receipt = recorder(episode)
        state = self._state.snapshot().value
        durable_episode_count = self.storage.count_episodes()
        durable_total_count = self.storage.count_memory_records()
        needs_state_alignment = receipt.status == "duplicate" and (
            durable_episode_count != state.episodic_count
            or durable_total_count != state.total_count
        )
        if receipt.status == "committed" or needs_state_alignment:
            self._commit_state(
                source_event_ids=tuple(
                    EventId(value) for value in episode.source_event_ids
                ),
                causation_id=EventId(f"memory-episode:{episode.episode_id}"),
            )
        return receipt

    def recall(self, request: RecallRequest) -> RecallBundle:
        """Return a bounded provenance-bearing RecallBundle for reasoning."""
        recall = getattr(self.storage, "recall", None)
        if not callable(recall):
            raise TypeError("the configured Memory store does not support RecallBundle")
        # The storage adapter owns candidate selection; the facade binds the
        # result to the current semantic revision so a later outcome cannot
        # settle a proposal against an obsolete snapshot.
        return replace(recall(request), recall_revision=self.revision)

    def submit_memory_use_proposal(
        self, proposal: MemoryUseProposal, bundle: RecallBundle
    ) -> bool:
        """Record bounded IDs a reasoning turn says it actually adopted.

        A proposal is only an allow-list check.  It never changes Memory and
        cannot be treated as a reinforcement receipt until an independent
        authoritative outcome is supplied.
        """
        if proposal.recall_revision != self.revision:
            raise ValueError("memory-use proposal revision is stale")
        if bundle.recall_revision != proposal.recall_revision:
            raise ValueError("memory-use proposal does not match Recall revision")
        available = {
            "episode": {item.episode_id for item in bundle.episodes},
            "node": {item.node_id for item in bundle.focus_nodes},
            "assertion": {item.assertion_id for item in bundle.assertions},
        }[proposal.target_kind]
        if not set(proposal.target_ids) <= available:
            raise ValueError(
                "memory-use proposal references an ID outside RecallBundle"
            )
        existing = self._use_proposals.get(proposal.proposal_id)
        if existing is not None:
            if existing != proposal:
                raise ValueError(
                    "memory-use proposal ID was reused with different content"
                )
            return False
        if len(self._use_proposal_order) == self._use_proposal_order.maxlen:
            oldest = self._use_proposal_order.popleft()
            self._use_proposals.pop(oldest, None)
        self._use_proposal_order.append(proposal.proposal_id)
        self._use_proposals[proposal.proposal_id] = proposal
        return True

    def consume_reinforcement_receipt(
        self, receipt: QualifiedReinforcementReceipt
    ) -> bool:
        """Settle one authoritative outcome into the storage-owned policy."""
        proposal = None
        if receipt.proposal_id is not None:
            proposal = self._use_proposals.get(receipt.proposal_id)
            if proposal is None:
                raise ValueError("reinforcement receipt references an unknown proposal")
            if (
                receipt.target_kind != proposal.target_kind
                or receipt.target_id not in proposal.target_ids
            ):
                raise ValueError(
                    "reinforcement target is not in the proposed Recall IDs"
                )
            if receipt.recall_revision != proposal.recall_revision:
                raise ValueError(
                    "reinforcement receipt revision does not match proposal"
                )
            if _parse_timestamp(receipt.occurred_at) < _parse_timestamp(
                proposal.occurred_at
            ):
                raise ValueError(
                    "reinforcement outcome cannot precede its use proposal"
                )
        elif receipt.outcome_kind != "independent_evidence":
            raise ValueError("non-evidence reinforcement requires a MemoryUseProposal")
        consumer = getattr(self.storage, "consume_reinforcement_receipt", None)
        if not callable(consumer):
            raise TypeError(
                "the configured Memory store does not support reinforcement receipts"
            )
        accepted = bool(consumer(receipt))
        if accepted:
            self._commit_state(
                causation_id=EventId(f"memory-reinforcement:{receipt.event_id}")
            )
        return accepted

    def render_recall(
        self,
        request: RecallRequest,
        *,
        character_limit: int | None = None,
    ) -> str:
        """Return the stable text projection of a typed recall result."""
        return render_recall_bundle(
            self.recall(request), character_limit=character_limit
        )

    def commit_episode_candidate(
        self,
        candidate: EpisodicMemoryCandidate,
    ) -> StateCommitReceipt:
        """Validate and commit one explicit Turn candidate exactly once."""
        with self._episode_candidate_lock:
            if candidate.candidate_id in self._committed_episode_candidate_ids:
                return StateCommitReceipt(
                    candidate_id=candidate.candidate_id,
                    status=StateCommitStatus.DUPLICATE,
                    revision=self.revision,
                    reason="candidate_already_committed",
                )
            if candidate.base_revision != self.revision:
                return StateCommitReceipt(
                    candidate_id=candidate.candidate_id,
                    status=StateCommitStatus.STALE,
                    revision=self.revision,
                    reason="base_revision_mismatch",
                )
            return self._commit_source_first_candidate(candidate)

    def _commit_source_first_candidate(
        self,
        candidate: EpisodicMemoryCandidate,
    ) -> StateCommitReceipt:
        intensity = (
            candidate.intensity / 100.0
            if candidate.intensity > 1.0
            else candidate.intensity
        )
        episode_id = EventId(f"memory-episode:{candidate.candidate_id}")
        episode = ClosedEpisode(
            episode_id=str(episode_id),
            idempotency_key=str(candidate.candidate_id),
            occurred_from=candidate.created_at.isoformat(),
            content_text=candidate.content,
            event_kind="completed_interaction",
            source_event_ids=tuple(str(value) for value in candidate.source_event_ids),
            importance=max(0.0, min(1.0, intensity)),
            emotion=candidate.emotion,
            emotion_intensity=max(0.0, min(1.0, intensity)),
            stimulus=candidate.stimulus,
            metadata={
                "candidate_id": str(candidate.candidate_id),
                "source_event_ids": [
                    str(value) for value in candidate.source_event_ids
                ],
            },
        )
        receipt = self.storage.record_episode(episode)
        status = (
            StateCommitStatus.COMMITTED
            if receipt.status == "committed"
            else StateCommitStatus.DUPLICATE
        )
        if status is StateCommitStatus.COMMITTED:
            self._commit_state(
                source_event_ids=candidate.source_event_ids,
                causation_id=candidate.candidate_id,
            )
        if len(self._committed_episode_candidate_order) == 2048:
            oldest = self._committed_episode_candidate_order[0]
            self._committed_episode_candidate_ids.discard(oldest)
        self._committed_episode_candidate_order.append(candidate.candidate_id)
        self._committed_episode_candidate_ids.add(candidate.candidate_id)
        return StateCommitReceipt(
            candidate_id=candidate.candidate_id,
            status=status,
            revision=self.revision,
            reason="episode_already_present"
            if status is StateCommitStatus.DUPLICATE
            else None,
        )

    def pending_consolidation_ids(self, limit: int = 8) -> tuple[str, ...]:
        """Return a bounded wake-up view for the single maintenance owner.

        The scheduler may need to wake for Lifecycle-only work even when no
        Episode is awaiting projection.  The sentinel is operational input to
        the existing consolidation candidate, not a new Memory record or
        queue; ``run_maintenance`` still owns the ordered stages.
        """
        if limit < 1:
            return ()
        pending = getattr(self.storage, "pending_episodes", None)
        if not callable(pending):
            raise TypeError(
                "the configured Memory store does not expose pending Episodes"
            )
        episode_ids = tuple(episode.episode_id for episode in pending(limit=limit))
        if episode_ids:
            return episode_ids
        due = getattr(self.storage, "has_due_lifecycle", None)
        if callable(due) and due():
            return ("maintenance:lifecycle",)
        return ()

    def run_consolidation(
        self,
        model_port: MemoryModelPort | None = None,
        *,
        max_episodes: int | None = None,
    ) -> Dict[str, Any]:
        """运行巩固流程

        Args:
            model_port: LLM运行时代理（可选）

        Returns:
            巩固结果字典
            {"consolidated_count": int, "knowledge_created": int, "edges_created": int}
        """
        result = self.consolidator.run_consolidation(
            model_port,
            max_episodes=max_episodes,
        )
        if any(isinstance(value, int) and value > 0 for value in result.values()):
            self._commit_state(
                causation_id=EventId(f"memory-consolidation:{uuid4().hex}")
            )
        return result

    def run_consolidation_batch(
        self,
        request: ConsolidationRequest,
        model_port: MemoryModelPort | None = None,
    ) -> ConsolidationBatchReceipt:
        """Execute one typed, bounded background worker pass."""
        receipt = self.consolidator.run_batch(request, model_port=model_port)
        if receipt.consolidated_episode_ids or receipt.failed_episode_ids:
            self._commit_state(
                causation_id=EventId(
                    f"memory-consolidation-batch:{request.worker_id}:{uuid4().hex}"
                )
            )
        return receipt

    def run_maintenance(
        self,
        request: MaintenanceRequest | None = None,
        model_port: MemoryModelPort | None = None,
    ) -> MaintenanceReceipt:
        """Run the Memory-owned ordered Consolidation then Lifecycle stages."""
        resolved = request or MaintenanceRequest()
        batch = self.consolidator.run_batch(
            ConsolidationRequest(
                max_episodes=resolved.max_episodes,
                worker_id=resolved.worker_id,
                checkpoint=resolved.checkpoint,
                lease_seconds=resolved.lease_seconds,
            ),
            model_port=model_port,
        )
        processed_for_budget = len(batch.consolidated_episode_ids) + len(
            batch.failed_episode_ids
        )
        remaining_budget = max(0, resolved.max_episodes - processed_for_budget)
        lifecycle = getattr(self.storage, "run_lifecycle", None)
        if not callable(lifecycle) or remaining_budget == 0:
            score_control_errors = self._compact_score_control(
                max_targets=resolved.max_episodes
            )
            batch_errors = {**dict(batch.errors), **score_control_errors}
            status = (
                "partial"
                if batch_errors
                and (batch.failed_episode_ids or batch.consolidated_episode_ids)
                else "failed"
                if batch_errors
                else "completed"
                if batch.consolidated_episode_ids
                else "empty"
            )
            result = MaintenanceReceipt(
                worker_id=resolved.worker_id,
                status=status,  # type: ignore[arg-type]
                consolidated_episode_ids=batch.consolidated_episode_ids,
                knowledge_created=batch.nodes_created,
                edges_created=batch.assertions_created,
                evidence_created=batch.evidence_created,
                failed_episode_ids=batch.failed_episode_ids,
                checkpoint=batch.checkpoint or resolved.checkpoint,
                errors=batch_errors,
            )
            if result.consolidated_episode_ids or result.failed_episode_ids:
                self._commit_state(
                    causation_id=EventId(f"memory-maintenance:{uuid4().hex}")
                )
            return result
        lifecycle_receipt = lifecycle(
            MaintenanceRequest(
                max_episodes=remaining_budget,
                worker_id=resolved.worker_id,
                checkpoint=batch.checkpoint or resolved.checkpoint,
                lease_seconds=resolved.lease_seconds,
            )
        )
        score_control_errors = self._compact_score_control(
            max_targets=resolved.max_episodes
        )
        errors = {
            **dict(batch.errors),
            **dict(lifecycle_receipt.errors),
            **score_control_errors,
        }
        if batch.failed_episode_ids:
            status = (
                "partial"
                if (
                    batch.consolidated_episode_ids
                    or lifecycle_receipt.lifecycle_episode_ids
                    or lifecycle_receipt.lifecycle_node_ids
                    or lifecycle_receipt.lifecycle_assertion_ids
                )
                else "failed"
            )
        elif lifecycle_receipt.status == "empty" and not batch.consolidated_episode_ids:
            status = "failed" if errors else "empty"
        else:
            status = "partial" if errors else "completed"
        result = MaintenanceReceipt(
            worker_id=resolved.worker_id,
            status=status,  # type: ignore[arg-type]
            consolidated_episode_ids=batch.consolidated_episode_ids,
            lifecycle_episode_ids=lifecycle_receipt.lifecycle_episode_ids,
            lifecycle_node_ids=lifecycle_receipt.lifecycle_node_ids,
            lifecycle_assertion_ids=lifecycle_receipt.lifecycle_assertion_ids,
            knowledge_created=batch.nodes_created,
            edges_created=batch.assertions_created,
            evidence_created=batch.evidence_created,
            failed_episode_ids=batch.failed_episode_ids,
            checkpoint=lifecycle_receipt.checkpoint
            or batch.checkpoint
            or resolved.checkpoint,
            errors=errors,
        )
        if any(
            (
                result.consolidated_episode_ids,
                result.lifecycle_episode_ids,
                result.lifecycle_node_ids,
                result.lifecycle_assertion_ids,
                result.failed_episode_ids,
            )
        ):
            self._commit_state(
                causation_id=EventId(f"memory-maintenance:{uuid4().hex}")
            )
        return result

    def _compact_score_control(self, *, max_targets: int) -> dict[str, str]:
        """Run bounded receipt/checkpoint housekeeping after lifecycle work."""
        compactor = getattr(self.storage, "compact_score_control", None)
        if not callable(compactor):
            return {}
        try:
            # The returned counters are operational diagnostics.  Semantic
            # values were already materialized by the idempotent replay path;
            # compaction itself must not advance the Memory revision.
            compactor(max_targets=max_targets)
        except Exception as error:  # noqa: BLE001 - maintenance remains retryable
            logger.warning("Memory score-control compaction failed: %s", error)
            return {"score_control": str(error)}
        return {}

    @property
    def revision(self) -> int:
        """Return the committed semantic memory-state revision."""
        return self._state.snapshot().revision

    @property
    def uses_typed_memory(self) -> bool:
        """Whether this facade is backed by the source-first Memory contract."""
        return self._typed_memory

    def snapshot(
        self,
        captured_at: datetime | None = None,
    ) -> MemoryStateSnapshot:
        """Return durable-memory counts and provenance at a context cutoff."""
        state = self._state.snapshot().value
        return state.model_copy(update={"captured_at": captured_at or self._clock()})

    def checkpoint(self) -> StateCheckpoint[MemoryStateSnapshot]:
        """Return a persistence-neutral checkpoint for memory continuity."""
        return self._state.checkpoint()

    def validate_checkpoint(
        self,
        checkpoint: StateCheckpoint[MemoryStateSnapshot],
    ) -> None:
        """Validate revision and durable-store containment before restore."""
        current = self._state.snapshot()
        if checkpoint.revision < current.revision:
            raise StateRestoreError(
                "memory checkpoint revision is older than current state"
            )
        current_episodic = self.storage.count_episodes()
        current_total = self.storage.count_memory_records()
        if current_episodic < checkpoint.value.episodic_count:
            raise StateRestoreError(
                "memory store no longer contains the checkpoint episodic state"
            )
        if current_total < checkpoint.value.total_count:
            raise StateRestoreError(
                "memory store no longer contains the checkpoint state"
            )

    def restore(
        self,
        checkpoint: StateCheckpoint[MemoryStateSnapshot],
    ) -> None:
        """Restore continuity metadata only after the durable store is present."""
        self.validate_checkpoint(checkpoint)
        self._state.restore(checkpoint)

    def memory_inspection_snapshot(
        self,
        *,
        episode_limit: int = 1000,
        node_limit: int = 1000,
        assertion_limit: int = 800,
    ) -> MemoryInspectionSnapshot:
        """Return a bounded typed view for authorized developer projections."""
        read_episodes = cast(Callable[..., Any], self.storage.list_episodes)
        read_nodes = cast(Callable[..., Any], self.storage.list_graph_nodes)
        read_assertions = cast(Callable[..., Any], self.storage.list_graph_assertions)
        return MemoryInspectionSnapshot(
            episodes=tuple(read_episodes(limit=episode_limit)),
            nodes=tuple(read_nodes(limit=node_limit)),
            assertions=tuple(read_assertions(limit=assertion_limit)),
        )

    def close(self) -> None:
        """Retain the injected store's lifecycle for Bootstrap ownership."""
        return None

    def _commit_state(
        self,
        *,
        source_event_ids: tuple[EventId, ...] = (),
        causation_id: EventId | None = None,
    ) -> None:
        """Advance the semantic revision after a successful storage mutation."""
        with self._state_commit_lock:
            current = self._state.snapshot()
            captured_at = self._clock()
            value = current.value.model_copy(
                update={
                    "revision": current.revision + 1,
                    "captured_at": captured_at,
                    "episodic_count": self.storage.count_episodes(),
                    "total_count": self.storage.count_memory_records(),
                    "source_event_ids": tuple(dict.fromkeys(source_event_ids)),
                    "snapshot_freshness": "current",
                }
            )
            candidate = StateCandidate(
                candidate_id=EventId(f"memory-state:{uuid4().hex}"),
                owner="memory",
                base_revision=current.revision,
                source_event_ids=value.source_event_ids,
                causation_id=causation_id,
                created_at=captured_at,
                value=value,
            )
            receipt = self._state.commit(candidate)
            if receipt.status is not StateCommitStatus.COMMITTED:
                raise RuntimeError(
                    f"memory state commit failed: {receipt.status.value}"
                )
