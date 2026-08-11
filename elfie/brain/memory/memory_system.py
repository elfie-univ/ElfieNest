"""记忆系统门面：组合所有子系统，提供统一API。

MemorySystem 是图记忆系统的统一入口门面（Facade），
将所有子系统组合在一起，对外暴露简洁的 API 接口。

子系统列表：
- KnowledgeStore: final SQLite knowledge storage
- SensoryBuffer: 短期感知缓冲
- CoreCognition: 核心认知（4段人格信念）
- MemoryEncoder: 编码引擎
- MemoryRetriever: 多维检索引擎
- SpreadingActivation: 扩散激活
- EbbinghausDecay: 衰减遗忘计算
- EmotionWeighting: 情绪自适应加权
- MemoryConsolidator: 巩固引擎
- ContextAssembler: 5区域上下文组装
- SensoryIndexer: 感官索引
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .consolidation import MemoryConsolidator
from .context_assembly import ContextAssembler
from .core_cognition import CoreCognition
from .ebbinghaus_decay import EbbinghausDecay
from .emotion_weighting import EmotionWeighting
from .encoding import MemoryEncoder
from .knowledge_store import KnowledgeStore
from .memory_store import MemoryStorePort
from .node_types import RetrievalQuery
from .retrieval import MemoryRetriever
from .sensory_buffer import SensoryBuffer
from .sensory_index import SensoryIndexer
from .spreading_activation import SpreadingActivation

logger = logging.getLogger("elfie.brain.memory.memory_system")


class MemorySystem:
    """记忆系统门面：组合所有子系统，提供统一API"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        personality_path: Optional[str] = None,
        elfie_id: str | None = None,
        config_dir: str | None = None,
        personality_data: Optional[dict] = None,
        storage: MemoryStorePort | None = None,
    ):
        """初始化所有组件

        Args:
            db_path: SQLite数据库路径（默认:memory:用于测试）
            personality_path: personality.yaml路径（默认自动查找）
        """
        resolved_db_path = db_path
        if storage is None and resolved_db_path is None:
            resolved_db_path = (
                str(Path(config_dir) / "memory" / "knowledge.sqlite")
                if config_dir is not None
                else ":memory:"
            )
        if storage is None:
            self.storage: MemoryStorePort = KnowledgeStore(
                resolved_db_path or ":memory:"
            )
            self._owns_storage = True
        else:
            self.storage = storage
            self._owns_storage = False
        self.sensory_buffer = SensoryBuffer()
        self.core_cognition = CoreCognition(
            resolved_db_path or ":memory:",
            personality_path,
            personality_data=personality_data,
            storage=self.storage,
        )
        self.sensory_indexer = SensoryIndexer(self.storage)
        self.encoder = MemoryEncoder(
            self.storage,
            self.sensory_buffer,
            self.sensory_indexer,
            elfie_id=elfie_id,
            config_dir=config_dir,
        )
        self.retriever = MemoryRetriever(self.storage)
        self.spreading = SpreadingActivation(self.storage)
        self.decay = EbbinghausDecay()
        self.weighting = EmotionWeighting()
        self.consolidator = MemoryConsolidator(
            self.storage,
            self.core_cognition,
            elfie_id=elfie_id,
            config_dir=config_dir,
        )
        self.context_assembler = ContextAssembler(
            self.storage,
            self.retriever,
            self.spreading,
            self.decay,
            self.weighting,
            self.core_cognition,
        )

    def bind_elfie_identity(
        self,
        elfie_id: str,
        config_dir: str | None = None,
    ) -> None:
        self.encoder.elfie_id = elfie_id
        self.consolidator.elfie_id = elfie_id
        if config_dir is not None:
            self.encoder.config_dir = config_dir
            self.consolidator.config_dir = config_dir

    def record_episode(
        self,
        content: Optional[str] = None,
        emotion: str = "calm",
        intensity: float = 0.0,
        stimulus: Optional[str] = None,
        sensory: Optional[dict] = None,
        runtime_agent=None,
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
            runtime_agent: LLM运行时代理（可选）

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
        return self.encoder.encode(event, emo, inte, stimulus, sensory, runtime_agent)

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

    def run_consolidation(self, runtime_agent=None) -> Dict[str, Any]:
        """运行巩固流程

        Args:
            runtime_agent: LLM运行时代理（可选）

        Returns:
            巩固结果字典
            {"consolidated_count": int, "knowledge_created": int, "edges_created": int}
        """
        return self.consolidator.run_consolidation(runtime_agent)

    def get_core_cognition(self) -> Dict[str, str]:
        """获取核心认知文本

        Returns:
            {identity: str, relation: str, world: str, tendency: str}
        """
        return self.core_cognition.get_core_text()

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

    def get_context(
        self,
        query: str,
        emotion: str = "calm",
        intensity: float = 0.0,
        entities: Optional[List[str]] = None,
        current_time: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """获取5区域上下文文本

        构造RetrievalQuery并调用context_assembler.assemble()，
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
        return self.context_assembler.assemble(retrieval_query, top_k=top_k)

    def close(self) -> None:
        """Close the final knowledge database owned by this facade."""
        if self._owns_storage:
            self.storage.close()
