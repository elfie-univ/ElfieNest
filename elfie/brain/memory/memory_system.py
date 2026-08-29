"""记忆系统门面：统一暴露 source-first Memory API。

``MemorySystem`` 是图记忆系统的统一入口门面（Facade）。生产 SQLite
适配器只走 ``Episode → Graph → Evidence → RecallBundle`` 主线；旧的
编码、检索、格式化和感官组件仅在尚未迁移的语义 Fake/兼容调用方中按需
构造，不构成第二套生产事实源。
"""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, cast
from uuid import uuid4

from elfie.brain.memory.contracts import MemoryStateSnapshot
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
    RecallBundle,
    RecallRequest,
)
from .memory_store import MemoryStorePort
from .model_food import MemoryModelPort
from .node_types import MemoryNode, RetrievalQuery
from .recall_renderer import render_recall_bundle

logger = logging.getLogger("elfie.brain.memory.memory_system")


class MemorySystem:
    """记忆系统门面：组合所有子系统，提供统一API"""

    def __init__(
        self,
        storage: MemoryStorePort,
        *,
        elfie_id: str | None = None,
        personality_data: Optional[dict] = None,
        clock: Callable[[], datetime] | None = None,
        initial_at: datetime | None = None,
    ):
        """初始化 typed Memory 主线；具体存储由 Bootstrap 注入。"""
        self.storage = storage
        self._personality_data = dict(personality_data or {})
        self._typed_memory = _supports_typed_memory(storage)
        if elfie_id is not None:
            binder = getattr(storage, "bind_elfie_identity", None)
            if callable(binder):
                binder(elfie_id)
        self._owns_storage = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        state_at = initial_at or self._clock()
        total_count = storage.count_nodes()
        initial_state = MemoryStateSnapshot(
            revision=0,
            captured_at=state_at,
            episodic_count=storage.count_nodes("episodic"),
            total_count=total_count,
            freshness="current" if total_count else "unknown",
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
        # The target SQLite adapter has one source-first Memory path.  The
        # pre-contract components remain available only for semantic Fakes and
        # old developer tools while their callers are being migrated; they are
        # not constructed during production initialization.
        self.sensory_buffer: Any = None
        self.self_narrative: Any = None
        self.sensory_indexer: Any = None
        self.encoder: Any = None
        self.retriever: Any = None
        self.spreading: Any = None
        self.decay: Any = None
        self.weighting: Any = None
        self.recall_formatter: Any = None
        if not self._typed_memory:
            from .ebbinghaus_decay import EbbinghausDecay
            from .emotion_weighting import EmotionWeighting
            from .encoding import MemoryEncoder
            from .recall_formatter import MemoryRecallFormatter
            from .retrieval import MemoryRetriever
            from .self_narrative import MemorySelfNarrativeProjection
            from .sensory_buffer import SensoryBuffer
            from .sensory_index import SensoryIndexer
            from .spreading_activation import SpreadingActivation

            self.sensory_buffer = SensoryBuffer()
            self.self_narrative = MemorySelfNarrativeProjection(
                storage=storage,
                personality_data=personality_data,
            )
            self.sensory_indexer = SensoryIndexer(self.storage)
            self.encoder = MemoryEncoder(
                self.storage,
                self.sensory_buffer,
                self.sensory_indexer,
                elfie_id=elfie_id,
            )
            self.retriever = MemoryRetriever(self.storage)
            self.spreading = SpreadingActivation(self.storage)
            self.decay = EbbinghausDecay()
            self.weighting = EmotionWeighting()
            self.recall_formatter = MemoryRecallFormatter(
                self.storage,
                self.retriever,
                self.spreading,
                self.decay,
                self.weighting,
                self.self_narrative,
            )
        else:
            self.recall_formatter = None
        self.consolidator = MemoryConsolidator(
            self.storage,
            self.self_narrative,
            elfie_id=elfie_id,
        )

    def bind_elfie_identity(
        self,
        elfie_id: str,
    ) -> None:
        binder = getattr(self.storage, "bind_elfie_identity", None)
        if callable(binder):
            binder(elfie_id)
        if self.encoder is not None:
            self.encoder.elfie_id = elfie_id
        self.consolidator.elfie_id = elfie_id

    def record_closed_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        """Persist one already-closed Episode through the source-first contract."""
        recorder = getattr(self.storage, "record_episode", None)
        if not callable(recorder):
            raise TypeError("the configured Memory store does not support Episodes")
        receipt = recorder(episode)
        if receipt.status == "committed":
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
        return recall(request)

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

    def record_episode(
        self,
        content: Optional[str] = None,
        emotion: str = "calm",
        intensity: float = 0.0,
        stimulus: Optional[str] = None,
        sensory: Optional[dict] = None,
        model_port: MemoryModelPort | None = None,
        source_event_ids: tuple[EventId, ...] = (),
        # 兼容旧API关键字参数名
        event_description: Optional[str] = None,
        emotion_tag: Optional[str] = None,
        emotion_intensity: Optional[float] = None,
    ) -> str:
        """记录事件（兼容旧API签名）

        同时支持新旧两组参数名：
        - 新: content, emotion, intensity
        - 旧: event_description, emotion_tag, emotion_intensity

        Args:
            content: 事件内容
            emotion: 情绪标签
            intensity: 情绪强度 (0~100)
            stimulus: 刺激源
            sensory: 感官数据字典
            model_port: LLM运行时代理（可选）

        Returns:
            typed 主线返回创建的 Episode ID；旧兼容路径返回 episodic 节点 ID，
            并保留其低强度/无刺激源规则。
        """
        event = event_description if event_description is not None else content
        emo = emotion_tag if emotion_tag is not None else emotion
        inte = emotion_intensity if emotion_intensity is not None else intensity
        if event is None:
            raise TypeError(
                "record_episode() missing required argument: 'content' or 'event_description'"
            )
        if not self._typed_memory:
            node_id = self.encoder.encode(
                event,
                emo,
                inte,
                stimulus,
                sensory,
                model_port,
                source_event_ids,
            )
            self._commit_state(
                source_event_ids=source_event_ids,
                causation_id=EventId(f"memory-record:{uuid4().hex}"),
            )
            return node_id

        del model_port
        normalized_intensity = float(inte)
        if normalized_intensity > 1.0:
            normalized_intensity /= 100.0
        normalized_intensity = max(0.0, min(1.0, normalized_intensity))
        source_key = "|".join(str(value) for value in source_event_ids)
        identity = (
            hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
            if source_key
            else uuid4().hex
        )
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        sensory_pairs = tuple(
            (str(key), str(value)) for key, value in (sensory or {}).items()
        )
        receipt = self.record_closed_episode(
            ClosedEpisode(
                episode_id=f"memory-episode:{identity}",
                idempotency_key=f"memory-record:{identity}",
                occurred_from=now.isoformat(),
                content_text=event,
                event_kind="interaction",
                source_event_ids=tuple(str(value) for value in source_event_ids),
                importance=normalized_intensity,
                emotion=emo,
                emotion_intensity=normalized_intensity,
                stimulus=stimulus,
                sensory=sensory_pairs,
                metadata={"source": "memory.record_episode"},
            )
        )
        return receipt.episode_id

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
            # A production SQLite adapter owns the source-first Episode
            # contract.  Completed interaction candidates already represent a
            # closed event, so they must bypass the legacy intensity gate and
            # become one durable, idempotent Episode.  Semantic Fakes retain
            # the historical encoder path used by focused algorithm tests.
            recorder = getattr(self.storage, "record_episode", None)
            if callable(recorder):
                return self._commit_source_first_candidate(candidate)
            self.encoder.encode(
                candidate.content,
                candidate.emotion,
                candidate.intensity,
                candidate.stimulus,
                None,
                None,
                candidate.source_event_ids,
            )
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
                status=StateCommitStatus.COMMITTED,
                revision=self.revision,
            )

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

    def retrieve_relevant_memories(
        self,
        query: str,
        top_k: int = 5,
        current_emotion: Optional[str] = None,
    ) -> List[str]:
        """检索相关记忆（兼容旧API签名）

        构造RetrievalQuery并调用retriever检索，
        返回记忆内容的文本列表。

        Args:
            query: 查询文本
            top_k: 返回结果数量上限
            current_emotion: 当前情绪（用于情绪加权检索）

        Returns:
            记忆内容文本列表
        """
        if self._typed_memory:
            bundle = self.recall(
                RecallRequest(
                    text=query,
                    mode="basic_local",
                    seed_limit=max(0, min(top_k * 2, 8)),
                    node_limit=max(0, min(top_k * 4, 40)),
                    episode_limit=max(0, min(top_k, 8)),
                )
            )
            values = [episode.excerpt for episode in bundle.episodes]
            values.extend(
                node.label for node in bundle.focus_nodes if node.label not in values
            )
            return list(dict.fromkeys(values))[: max(0, top_k)]
        retrieval_query = RetrievalQuery(
            text_query=query,
            current_emotion=current_emotion or "",
        )
        nodes = self.retriever.retrieve(retrieval_query, top_k)
        return [node.content for node in nodes]

    def recall_nodes(
        self,
        query: str,
        *,
        emotion: str = "",
        intensity: float = 0.0,
        current_time: str = "",
        top_k: int = 5,
    ) -> list[MemoryNode]:
        """Return the durable nodes selected for one reasoning context.

        The reasoning boundary needs node identity and provenance, not a
        preformatted narrative string.  Formatting remains a presentation
        concern; this method exposes only the typed storage nodes selected by
        the existing retriever.
        """
        recall = getattr(self.storage, "recall", None)
        if callable(recall):
            bundle = recall(
                RecallRequest(
                    text=query,
                    mode="basic_local",
                    seed_limit=max(1, min(top_k * 2, 8)),
                    node_limit=max(1, min(top_k * 4, 400)),
                    episode_limit=max(1, min(top_k, 80)),
                )
            )
            ids = [node.node_id for node in bundle.focus_nodes]
            ids.extend(episode.episode_id for episode in bundle.episodes)
            result: list[MemoryNode] = []
            seen: set[str] = set()
            for node_id in ids:
                if node_id in seen:
                    continue
                node = self.storage.get_node(node_id)
                if node is None or node.metadata.get("recall_eligible") is False:
                    continue
                seen.add(node_id)
                result.append(node)
                if len(result) >= top_k:
                    break
            return result
        retrieval_query = RetrievalQuery(
            text_query=query,
            current_emotion=emotion,
            current_intensity=intensity,
            current_time=current_time,
        )
        return self.retriever.retrieve(retrieval_query, top_k)

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
        if callable(pending):
            episode_ids = tuple(episode.episode_id for episode in pending(limit=limit))
        else:
            episode_ids = tuple(
                node.id
                for node in self.storage.get_unconsolidated_nodes(node_type="episodic")[
                    :limit
                ]
            )
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
            status = (
                "partial"
                if batch.failed_episode_ids and batch.consolidated_episode_ids
                else "failed"
                if batch.failed_episode_ids
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
                errors=batch.errors,
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
        errors = {**dict(batch.errors), **dict(lifecycle_receipt.errors)}
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
            status = "empty"
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
        current_episodic = self.storage.count_nodes("episodic")
        current_total = self.storage.count_nodes()
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

    def get_self_narrative(self) -> Dict[str, str]:
        """获取核心认知文本

        Returns:
            {identity: str, relation: str, world: str, tendency: str}
        """
        if self.self_narrative is not None:
            return self.self_narrative.get_core_text()
        raw_description = self._personality_data.get("self_description")
        description = raw_description if isinstance(raw_description, str) else ""
        if not description:
            metadata = self._personality_data.get("metadata")
            metadata_description = (
                metadata.get("description") if isinstance(metadata, dict) else None
            )
            if isinstance(metadata_description, str):
                description = metadata_description
        return {
            "identity": description,
            "relation": "",
            "world": "",
            "tendency": "",
        }

    def get_all_episodes(self) -> List[Dict[str, Any]]:
        """获取所有episodic节点（兼容旧API EpisodeMemoryManager.get_all_episodes()）

        将知识存储中的episodic节点转换为旧格式的字典列表，
        每个字典包含 content 和 metadata 键。

        Returns:
            [{"content": str, "metadata": dict}, ...]
        """
        if self._typed_memory:
            source_reader = getattr(self.storage, "list_episodes", None)
            typed_episodes = (
                source_reader(limit=1000) if callable(source_reader) else ()
            )
            return [
                {
                    "content": episode.content_text,
                    "metadata": {
                        "emotion": episode.emotion or "",
                        "timestamp": episode.occurred_from or "",
                        "intensity": episode.emotion_intensity or 0.0,
                        "importance": episode.importance,
                        "detail_level": episode.detail_level,
                        "lifecycle": episode.lifecycle,
                        "source_event_ids": list(episode.source_event_ids),
                    },
                }
                for episode in typed_episodes
            ]
        nodes = self.storage.get_nodes_by_type("episodic", limit=1000)
        episodes = []
        for node in nodes:
            episodes.append(
                {
                    "content": node.content,
                    "metadata": {
                        "emotion": node.metadata.get("emotion", ""),
                        "timestamp": node.metadata.get(
                            "timestamp", node.created_at or ""
                        ),
                        "intensity": node.metadata.get("emotion_intensity", 0.0),
                    },
                }
            )
        return episodes

    def memory_inspection_snapshot(
        self,
        *,
        episode_limit: int = 1000,
        node_limit: int = 1000,
        assertion_limit: int = 800,
    ) -> MemoryInspectionSnapshot:
        """Return a bounded typed view for authorized developer projections."""
        if not self._typed_memory:
            return MemoryInspectionSnapshot()
        episode_reader = getattr(self.storage, "list_episodes", None)
        node_reader = getattr(self.storage, "list_graph_nodes", None)
        assertion_reader = getattr(self.storage, "list_graph_assertions", None)
        if not (
            callable(episode_reader)
            and callable(node_reader)
            and callable(assertion_reader)
        ):
            return MemoryInspectionSnapshot()
        read_episodes = cast(Callable[..., Any], episode_reader)
        read_nodes = cast(Callable[..., Any], node_reader)
        read_assertions = cast(Callable[..., Any], assertion_reader)
        return MemoryInspectionSnapshot(
            episodes=tuple(read_episodes(limit=episode_limit)),
            nodes=tuple(read_nodes(limit=node_limit)),
            assertions=tuple(read_assertions(limit=assertion_limit)),
        )

    def recall_context(
        self,
        query: str,
        emotion: str = "calm",
        intensity: float = 0.0,
        entities: Optional[List[str]] = None,
        current_time: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """获取5区域上下文文本

        构造RetrievalQuery并调用recall_formatter.assemble()，
        返回格式化上下文文本（≤800 tokens）。

        Args:
            query: 查询文本
            emotion: 当前情绪
            intensity: 当前情绪强度
            entities: 当前涉及的实体列表
            current_time: 当前时间（ISO格式）
            top_k: 返回记忆条数（本地模型=1，远程API=5）

        Returns:
            结构化上下文文本
        """
        if self._typed_memory:
            del emotion, intensity, entities, current_time
            return self.render_recall(
                RecallRequest(
                    text=query,
                    mode="basic_local",
                    node_limit=max(0, min(top_k * 4, 40)),
                    episode_limit=max(0, min(top_k, 8)),
                    character_limit=12000,
                )
            )
        retrieval_query = RetrievalQuery(
            text_query=query,
            current_emotion=emotion,
            current_intensity=intensity,
            current_entities=entities or [],
            current_time=current_time or "",
        )
        formatter = self.recall_formatter
        if formatter is None:
            raise TypeError(
                "the configured Memory store does not support legacy recall"
            )
        return formatter.assemble(retrieval_query, top_k=top_k)

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
                    "episodic_count": self.storage.count_nodes("episodic"),
                    "total_count": self.storage.count_nodes(),
                    "source_event_ids": tuple(dict.fromkeys(source_event_ids)),
                    "freshness": "current",
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


def _supports_typed_memory(storage: MemoryStorePort) -> bool:
    """Detect the source-first contract without importing Infrastructure."""
    return all(
        callable(getattr(storage, name, None))
        for name in ("record_episode", "apply_consolidation", "recall")
    )
