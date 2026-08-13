"""记忆系统门面：组合所有子系统，提供统一API。

MemorySystem 是图记忆系统的统一入口门面（Facade），
将所有子系统组合在一起，对外暴露简洁的 API 接口。

子系统列表：
- MemoryStorePort: injected semantic memory persistence
- SensoryBuffer: 短期感知缓冲
- MemorySelfNarrativeProjection: 核心认知（4段人格信念）
- MemoryEncoder: 编码引擎
- MemoryRetriever: 多维检索引擎
- SpreadingActivation: 扩散激活
- EbbinghausDecay: 衰减遗忘计算
- EmotionWeighting: 情绪自适应加权
- MemoryConsolidator: 巩固引擎
- MemoryRecallFormatter: 5区域上下文组装
- SensoryIndexer: 感官索引
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Dict, List, Optional
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
from .ebbinghaus_decay import EbbinghausDecay
from .emotion_weighting import EmotionWeighting
from .encoding import MemoryEncoder
from .memory_store import MemoryStorePort
from .model_food import MemoryModelPort
from .node_types import RetrievalQuery
from .recall_formatter import MemoryRecallFormatter
from .retrieval import MemoryRetriever
from .self_narrative import MemorySelfNarrativeProjection
from .sensory_buffer import SensoryBuffer
from .sensory_index import SensoryIndexer
from .spreading_activation import SpreadingActivation

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
        """初始化所有语义组件；具体存储由 Bootstrap 注入。"""
        self.storage = storage
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
        self._committed_episode_candidate_ids: set[EventId] = set()
        self._committed_episode_candidate_order = deque(maxlen=2048)
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
        self.consolidator = MemoryConsolidator(
            self.storage,
            self.self_narrative,
            elfie_id=elfie_id,
        )
        self.recall_formatter = MemoryRecallFormatter(
            self.storage,
            self.retriever,
            self.spreading,
            self.decay,
            self.weighting,
            self.self_narrative,
        )

    def bind_elfie_identity(
        self,
        elfie_id: str,
    ) -> None:
        self.encoder.elfie_id = elfie_id
        self.consolidator.elfie_id = elfie_id

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
            创建的episodic节点ID，低强度无刺激源时返回空字符串
        """
        event = event_description if event_description is not None else content
        emo = emotion_tag if emotion_tag is not None else emotion
        inte = emotion_intensity if emotion_intensity is not None else intensity
        if event is None:
            raise TypeError(
                "record_episode() missing required argument: 'content' or 'event_description'"
            )
        node_id = self.encoder.encode(
            event,
            emo,
            inte,
            stimulus,
            sensory,
            model_port,
        )
        self._commit_state(
            source_event_ids=source_event_ids,
            causation_id=EventId(f"memory-record:{uuid4().hex}"),
        )
        return node_id

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
            self.encoder.encode(
                candidate.content,
                candidate.emotion,
                candidate.intensity,
                candidate.stimulus,
                None,
                None,
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
        retrieval_query = RetrievalQuery(
            text_query=query,
            current_emotion=current_emotion or "",
        )
        nodes = self.retriever.retrieve(retrieval_query, top_k)
        return [node.content for node in nodes]

    def pending_consolidation_ids(self, limit: int = 8) -> tuple[str, ...]:
        """Return a bounded, read-only view of episodic work awaiting consolidation."""
        if limit < 1:
            return ()
        return tuple(
            node.id
            for node in self.storage.get_unconsolidated_nodes(node_type="episodic")[
                :limit
            ]
        )

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

    @property
    def revision(self) -> int:
        """Return the committed semantic memory-state revision."""
        return self._state.snapshot().revision

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
        return self.self_narrative.get_core_text()

    def get_all_episodes(self) -> List[Dict[str, Any]]:
        """获取所有episodic节点（兼容旧API EpisodeMemoryManager.get_all_episodes()）

        将知识存储中的episodic节点转换为旧格式的字典列表，
        每个字典包含 content 和 metadata 键。

        Returns:
            [{"content": str, "metadata": dict}, ...]
        """
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
        retrieval_query = RetrievalQuery(
            text_query=query,
            current_emotion=emotion,
            current_intensity=intensity,
            current_entities=entities or [],
            current_time=current_time or "",
        )
        return self.recall_formatter.assemble(retrieval_query, top_k=top_k)

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
            raise RuntimeError(f"memory state commit failed: {receipt.status.value}")
