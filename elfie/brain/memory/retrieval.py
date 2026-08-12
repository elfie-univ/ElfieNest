"""多维检索引擎：从多个入口检索相关记忆"""

import logging
from datetime import datetime
from typing import Dict, List

from .memory_store import MemoryStorePort
from .node_types import EdgeTypes, MemoryNode, NodeTypes, RetrievalQuery

logger = logging.getLogger("elfie.brain.memory.retrieval")


class MemoryRetriever:
    """多维检索引擎：从多个入口检索相关记忆"""

    def __init__(self, storage: MemoryStorePort):
        self.storage = storage

    def retrieve(self, query: RetrievalQuery, top_k: int = 10) -> List[MemoryNode]:
        """主检索入口：综合多个维度检索相关记忆

        5个检索入口：
        1. text_query → TF-IDF语义匹配（调用search_by_content）
        2. current_entities → 通过involves边查找相关episodic
        3. current_time → 时间相近的episodic
        4. current_emotion → 同情绪的episodic
        5. current_sensory → 感官关键词匹配（sensory_index表）

        合并去重后返回top_k个节点
        """
        result_lists: List[List[MemoryNode]] = []

        if query.text_query:
            result_lists.append(self.retrieve_by_text(query.text_query, top_k))

        if query.current_entities:
            result_lists.append(self.retrieve_by_entity(query.current_entities, top_k))

        if query.current_time:
            result_lists.append(self.retrieve_by_time(query.current_time, top_k))

        if query.current_emotion:
            result_lists.append(self.retrieve_by_emotion(query.current_emotion, top_k))

        if query.current_sensory:
            result_lists.append(self.retrieve_by_sensory(query.current_sensory, top_k))

        return self._merge_and_deduplicate(result_lists, top_k)

    def retrieve_by_text(self, text_query: str, top_k: int = 5) -> List[MemoryNode]:
        """文字检索：仅返回可公开召回的情景记忆。"""
        results = self.storage.search_by_content(
            text_query,
            top_k,
            node_type=NodeTypes.EPISODIC.value,
        )
        nodes: List[MemoryNode] = []
        for node_id, score in results:
            node = self.storage.get_node(node_id)
            if node:
                node.metadata["_retrieval_score"] = score
                node.metadata["_retrieval_dimension"] = "text"
                nodes.append(node)
        return nodes

    def retrieve_by_entity(
        self, entity_names: List[str], top_k: int = 5
    ) -> List[MemoryNode]:
        """实体检索：通过involves边查找相关episodic

        先找到名称匹配的entity节点，然后沿着INVOLVES出边找到关联的episodic节点。
        """
        all_entity_nodes = self.storage.get_nodes_by_type(
            NodeTypes.ENTITY.value, limit=1000
        )
        matched_entities = [
            n
            for n in all_entity_nodes
            if any(name in n.content for name in entity_names)
        ]
        if not matched_entities:
            return []

        seen_ids: set = set()
        related: List[MemoryNode] = []

        for entity in matched_entities:
            edges = self.storage.get_edges(entity.id, direction="outgoing")
            for edge in edges:
                if edge.rel != EdgeTypes.INVOLVES.value:
                    continue
                if edge.target in seen_ids:
                    continue
                seen_ids.add(edge.target)
                node = self.storage.get_node(edge.target)
                if node:
                    node.metadata["_retrieval_score"] = edge.weight
                    node.metadata["_retrieval_dimension"] = "entity"
                    related.append(node)

        related.sort(key=lambda n: n.metadata.get("_retrieval_score", 0), reverse=True)
        return related[:top_k]

    def retrieve_by_time(self, current_time: str, top_k: int = 5) -> List[MemoryNode]:
        """时间检索：查找时间相近的episodic

        计算每个episodic节点与目标时间的时间差（24小时内），
        时间差越小得分越高，超过24小时不纳入。
        """
        try:
            target_time = datetime.fromisoformat(current_time)
        except (ValueError, TypeError):
            logger.warning("⏰ [时间检索] 无法解析时间: %s", current_time)
            return []

        episodic_nodes = self.storage.get_nodes_by_type(
            NodeTypes.EPISODIC.value, limit=1000
        )
        scored: List[MemoryNode] = []

        for node in episodic_nodes:
            node_time_str = node.metadata.get("timestamp") or node.created_at
            if not node_time_str:
                continue
            try:
                node_time = datetime.fromisoformat(node_time_str)
                diff_seconds = abs((node_time - target_time).total_seconds())
                if diff_seconds > 86400:
                    continue
                score = 1.0 - (diff_seconds / 86400.0)
                node.metadata["_retrieval_score"] = score
                node.metadata["_retrieval_dimension"] = "time"
                scored.append(node)
            except (ValueError, TypeError):
                continue

        scored.sort(key=lambda n: n.metadata.get("_retrieval_score", 0), reverse=True)
        return scored[:top_k]

    def retrieve_by_emotion(self, emotion: str, top_k: int = 5) -> List[MemoryNode]:
        """情绪检索：查找同情绪的episodic

        完全匹配得1.0分，部分匹配得0.5分。
        """
        episodic_nodes = self.storage.get_nodes_by_type(
            NodeTypes.EPISODIC.value, limit=1000
        )
        matched: List[MemoryNode] = []

        for node in episodic_nodes:
            node_emotion = node.metadata.get("emotion", "")
            if not node_emotion:
                continue
            if node_emotion == emotion:
                score = 1.0
            elif emotion in node_emotion or node_emotion in emotion:
                score = 0.5
            else:
                continue
            node.metadata["_retrieval_score"] = score
            node.metadata["_retrieval_dimension"] = "emotion"
            matched.append(node)

        matched.sort(key=lambda n: n.metadata.get("_retrieval_score", 0), reverse=True)
        return matched[:top_k]

    def retrieve_by_sensory(
        self, sensory: Dict[str, str], top_k: int = 5
    ) -> List[MemoryNode]:
        """感官检索：通过sensory_index表查找

        遍历每个(感官类型, 关键词)对，在sensory_index中匹配，
        累计匹配到的权重，返回权重最高的节点。
        """
        scored: Dict[str, float] = {}
        for node in self.storage.get_nodes_by_type(
            NodeTypes.EPISODIC.value, limit=1000
        ):
            indexed = node.metadata.get("sensory", {})
            if not isinstance(indexed, dict):
                continue
            for sense_type, sense_key in sensory.items():
                stored_key = indexed.get(sense_type, "")
                if sense_key and sense_key in stored_key:
                    scored[node.id] = scored.get(node.id, 0.0) + 0.8

        sorted_ids = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        nodes: List[MemoryNode] = []
        for node_id, score in sorted_ids[:top_k]:
            matched_node = self.storage.get_node(node_id)
            if matched_node:
                matched_node.metadata["_retrieval_score"] = score
                matched_node.metadata["_retrieval_dimension"] = "sensory"
                nodes.append(matched_node)

        return nodes

    def _merge_and_deduplicate(
        self, result_lists: List[List[MemoryNode]], top_k: int
    ) -> List[MemoryNode]:
        """合并多个检索结果，去重，返回top_k

        同一节点出现在多个检索维度时，得分累加（多维度匹配意味着更相关）。
        """
        if not result_lists:
            return []

        score_map: Dict[str, float] = {}

        for node_list in result_lists:
            for node in node_list:
                score = node.metadata.get("_retrieval_score", 0.5)
                score_map[node.id] = score_map.get(node.id, 0.0) + score

        sorted_ids = sorted(score_map.items(), key=lambda x: x[1], reverse=True)

        result: List[MemoryNode] = []
        for node_id, total_score in sorted_ids[:top_k]:
            matched_node = self.storage.get_node(node_id)
            if matched_node:
                matched_node.metadata["_retrieval_score"] = total_score
                result.append(matched_node)

        return result
