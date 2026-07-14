"""巩固引擎：将episodic记忆提炼为knowledge和entity属性更新。

8.5步骤巩固流程（含Pattern发现）：
1. 收集未巩固episodic节点（consolidated=False）
2. 按entity分组（通过involves边）
3. LLM知识提炼（每组经历总结规律/因果/偏好）→ ≤4次LLM调用
4. 创建knowledge节点（每条提炼结果→一个knowledge节点）
5. 建语义边（supports: knowledge→episodic, about: knowledge→entity）
6. 提取因果边和entity间关系边（LLM）
7. 更新entity属性（新发现的信息更新到entity.properties）
7.5 从knowledge中发现pattern，创建PATTERN节点，建implies边
8. 标记原始episodic为consolidated=True

安全性：
- LLM失败时保留所有原始数据，降级为规则提取
- 巩固是增量操作，只添加knowledge节点和边
- 永远不物理删除任何节点
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import EdgeTypes, MemoryNode, NodeTypes
from elfie.brain.memory.runtime_food import ask_memory_model
from elfie.brain.memory.tokenizer import tokenize

logger = logging.getLogger("elfie.brain.memory.consolidation")


class MemoryConsolidator:
    """巩固引擎：将episodic记忆提炼为knowledge和entity属性更新"""

    def __init__(
        self,
        storage: GraphStorage,
        core_cognition=None,
        elfie_id: str | None = None,
        config_dir: str | None = None,
    ):
        self.storage = storage
        self.core_cognition = core_cognition
        self._consolidation_count = 0  # 巩固次数计数
        self._knowledge_counter = 0  # 知识节点ID计数器
        self._pattern_counter = 0  # pattern节点ID计数器
        self._llm_calls_this_cycle = 0
        self._max_llm_calls = 4
        self.elfie_id = elfie_id
        self.config_dir = config_dir

    def run_consolidation(self, runtime_agent=None) -> Dict[str, Any]:
        """执行巩固流程（8.5步骤，含pattern发现）

        Steps:
        1-7: 同基础巩固流程
        7.5: 从knowledge节点中发现pattern，创建PATTERN节点，建implies边
        8:   标记consolidated

        Args:
            runtime_agent: 可选LLM运行时代理，提供ask()接口

        Returns:
            {"consolidated_count": int, "knowledge_created": int,
             "edges_created": int, "patterns_created": int}
        """
        self._llm_calls_this_cycle = 0
        result = {
            "consolidated_count": 0,
            "knowledge_created": 0,
            "edges_created": 0,
            "patterns_created": 0,
        }

        # 步骤1：收集未巩固episodic节点
        episodic_nodes = self._collect_unconsolidated()
        if not episodic_nodes:
            logger.info("巩固跳过：没有未巩固的episodic节点")
            return result

        logger.info("巩固开始：发现%d条未巩固episodic", len(episodic_nodes))

        # 步骤2：按entity分组（通过involves边）
        entity_groups = self._group_by_entity(episodic_nodes)

        all_knowledge_ids: List[str] = []
        all_source_ids: List[str] = []
        all_entity_ids: List[str] = []

        for entity_id, group_data in entity_groups.items():
            entity_node = group_data["entity_node"]
            group_nodes = group_data["nodes"]
            entity_name = entity_node.content if entity_node else "未知"
            source_ids = [n.id for n in group_nodes]

            all_source_ids.extend(source_ids)
            if entity_id != "_ungrouped_" and entity_node is not None:
                all_entity_ids.append(entity_id)

            if not group_nodes:
                continue

            # 步骤3：知识提炼（LLM优先，失败降级为规则提取）
            knowledge_items = self._extract_knowledge_with_llm(
                group_nodes,
                entity_name,
                runtime_agent,
            )
            if not knowledge_items:
                continue

            # 步骤4：创建knowledge节点
            knowledge_ids = self._create_knowledge_nodes(knowledge_items, source_ids)
            all_knowledge_ids.extend(knowledge_ids)

            # 步骤5：建语义边
            entity_ids_for_edges = [entity_id] if entity_id != "_ungrouped_" else []
            edge_count = self._build_semantic_edges(
                knowledge_ids,
                source_ids,
                entity_ids_for_edges,
            )
            result["edges_created"] += edge_count

            # 步骤6：提取因果边（LLM依赖，无LLM时跳过）
            causal_count = self._extract_causal_edges(
                group_nodes,
                runtime_agent,
            )
            result["edges_created"] += causal_count

            # 步骤7：更新entity属性（基于提取的知识）
            if entity_id != "_ungrouped_" and entity_node is not None:
                self._update_entity_properties(
                    entity_id,
                    entity_node,
                    knowledge_items,
                    group_nodes,
                )

        # 步骤7.5：从knowledge节点中发现pattern（规律抽象）
        if all_knowledge_ids:
            pattern_ids = self._discover_patterns(all_knowledge_ids, runtime_agent)
            result["patterns_created"] = len(pattern_ids)

        # 步骤8：标记原始episodic为consolidated=True
        self._mark_consolidated(all_source_ids)

        self._consolidation_count += 1
        result["consolidated_count"] = len(set(all_source_ids))
        result["knowledge_created"] = len(all_knowledge_ids)

        # 核心认知更新
        if self.core_cognition is not None:
            try:
                self.core_cognition.update(
                    consolidation_results=result,
                    runtime_agent=runtime_agent,
                )
            except Exception as e:
                logger.error("核心认知更新失败: %s", e)

        logger.info(
            "巩固完成：处理%d条episodic，创建%d个knowledge节点，%d个pattern，%d条边",
            result["consolidated_count"],
            result["knowledge_created"],
            result["patterns_created"],
            result["edges_created"],
        )
        return result

    # ------------------------------------------------------------------
    # 步骤1：收集
    # ------------------------------------------------------------------

    def _collect_unconsolidated(self) -> List[MemoryNode]:
        """步骤1：收集未巩固episodic节点"""
        return self.storage.get_unconsolidated_nodes(node_type="episodic")

    # ------------------------------------------------------------------
    # 步骤2：分组
    # ------------------------------------------------------------------

    def _group_by_entity(
        self,
        episodic_nodes: List[MemoryNode],
    ) -> Dict[str, Dict[str, Any]]:
        """步骤2：按entity分组（通过involves边）

        遍历每个episodic节点，查询其outgoing involves边，
        将关联到同一entity的episodic节点归为一组。
        没有关联实体的节点归入"_ungrouped_"组。

        Returns:
            {entity_id: {"entity_node": MemoryNode|None, "nodes": [MemoryNode, ...]}}
        """
        groups: Dict[str, Dict[str, Any]] = {}

        for node in episodic_nodes:
            # 从内存中的 edges 列表查找 involves 边
            involved_entities = [
                e.target for e in node.edges if e.rel == EdgeTypes.INVOLVES.value
            ]

            # 也查relational edges表（补充可能未同步到JSON列的数据）
            try:
                outgoing = self.storage.get_edges(node.id, direction="outgoing")
                for e in outgoing:
                    if (
                        e.rel == EdgeTypes.INVOLVES.value
                        and e.target not in involved_entities
                    ):
                        involved_entities.append(e.target)
            except Exception as e:
                logger.warning("实体分组查询失败: %s", e)

            if not involved_entities:
                # 没有关联实体的节点归入未分组
                groups.setdefault(
                    "_ungrouped_",
                    {
                        "entity_node": None,
                        "nodes": [],
                    },
                )["nodes"].append(node)
            else:
                for entity_id in involved_entities:
                    if entity_id not in groups:
                        entity_node = self.storage.get_node(entity_id)
                        groups[entity_id] = {
                            "entity_node": entity_node,
                            "nodes": [],
                        }
                    groups[entity_id]["nodes"].append(node)

        return groups

    # ------------------------------------------------------------------
    # 步骤3：知识提炼
    # ------------------------------------------------------------------

    def _extract_knowledge_with_llm(
        self,
        group: List[MemoryNode],
        entity_name: str,
        runtime_agent=None,
    ) -> List[Dict[str, Any]]:
        """步骤3：LLM知识提炼（降级为规则提取如果LLM不可用）

        优先使用LLM进行知识提取（每巩固周期≤4次调用）。
        LLM失败或不可用时降级为基于规则的提取。

        Returns:
            [{"content": str, "type": str, "confidence": float}, ...]
        """
        if (
            runtime_agent is not None
            and hasattr(runtime_agent, "ask")
            and self._llm_calls_this_cycle < self._max_llm_calls
        ):
            try:
                prompt = self._build_extraction_prompt(group, entity_name)
                response = ask_memory_model(
                    runtime_agent,
                    prompt,
                    elfie_id=self.elfie_id,
                    config_dir=self.config_dir,
                    food_key="focus",
                    complexity=2,
                )
                self._llm_calls_this_cycle += 1
                if response and response.strip():
                    items = self._parse_llm_response(response)
                    if items:
                        return items
            except Exception as e:
                logger.warning("LLM知识提炼失败: %s，降级为规则提取", e)

        # 降级：规则提取
        return self._rule_based_extraction(group, entity_name)

    def _build_extraction_prompt(
        self,
        group: List[MemoryNode],
        entity_name: str,
    ) -> str:
        """构建LLM知识提取提示"""
        episodes_text = "\n".join(
            f"- [{n.metadata.get('timestamp', 'unknown')}] {n.content}" for n in group
        )
        return (
            f"你是一个记忆巩固系统。以下是精灵小狐狸艾菲关于「{entity_name}」的多条经历：\n"
            f"{episodes_text}\n\n"
            "请提取出核心规律、因果关系、或偏好，以简短的陈述句输出，每行一条。\n"
            "示例：\n"
            "- 主人靠近时艾菲感到安全\n"
            "- 下雨天主人会带艾菲进屋\n"
            "- 被抚摸后情绪变好\n"
        )

    def _parse_llm_response(
        self,
        response: str,
    ) -> List[Dict[str, Any]]:
        """解析LLM返回的知识项"""
        items = []
        for line in response.strip().split("\n"):
            line = line.strip().lstrip("-* ").strip()
            if line and len(line) > 3:
                items.append(
                    {
                        "content": line,
                        "type": "knowledge",
                        "confidence": 0.8,
                    }
                )
        return items

    def _rule_based_extraction(
        self,
        group: List[MemoryNode],
        entity_name: str,
    ) -> List[Dict[str, Any]]:
        """基于规则的知识提取（LLM不可用时的降级方案）

        提取策略：
        1. 频率模式：经历次数≥3时记录为pattern
        2. 情绪模式：提取每条episodic中的情绪标签
        3. 重复情绪：如果所有记录情绪一致，提取为规律
        """
        knowledge_items: List[Dict[str, Any]] = []

        if not group:
            return knowledge_items

        # 频率模式：如果经历>=3次，提取为pattern
        if len(group) >= 3:
            knowledge_items.append(
                {
                    "content": f"与「{entity_name}」相关的经历出现{len(group)}次，是重要的互动对象",
                    "type": "pattern",
                    "confidence": min(0.9, 0.3 + len(group) * 0.1),
                }
            )

        # 提取各条episodic中的情绪信息
        for node in group:
            emotion = node.metadata.get("emotion", "")
            if emotion:
                knowledge_items.append(
                    {
                        "content": f"涉及「{entity_name}」时情绪为{emotion}",
                        "type": "knowledge",
                        "confidence": 0.6,
                    }
                )

        # 如果有重复情绪模式（所有记录情绪一致）
        emotions = [
            n.metadata.get("emotion", "")
            for n in group
            if n.metadata.get("emotion", "")
        ]
        if len(set(emotions)) == 1 and emotions:
            knowledge_items.append(
                {
                    "content": f"与「{entity_name}」互动时总是感到{emotions[0]}",
                    "type": "knowledge",
                    "confidence": 0.7,
                }
            )

        # 去重（基于content去重）
        seen_contents: set = set()
        unique_items = []
        for item in knowledge_items:
            if item["content"] not in seen_contents:
                seen_contents.add(item["content"])
                unique_items.append(item)

        return unique_items

    # ------------------------------------------------------------------
    # 步骤4：创建knowledge节点
    # ------------------------------------------------------------------

    def _create_knowledge_nodes(
        self,
        knowledge_items: List[Dict[str, Any]],
        source_ids: List[str],
    ) -> List[str]:
        """步骤4：创建knowledge节点

        每条提炼结果创建一个KNOWLEDGE类型节点，
        metadata中记录source_ids指向原始episodic。
        """
        knowledge_ids: List[str] = []
        now = datetime.now(timezone.utc).isoformat()

        for item in knowledge_items:
            self._knowledge_counter += 1
            node_id = (
                f"knowledge_c{self._consolidation_count}_n{self._knowledge_counter}"
            )
            node = MemoryNode(
                id=node_id,
                type=NodeTypes.KNOWLEDGE.value,
                content=item["content"],
                metadata={
                    "source_type": item.get("type", "knowledge"),
                    "confidence": item.get("confidence", 0.5),
                    "source_ids": source_ids,
                    "consolidation_round": self._consolidation_count,
                    "created_in_consolidation": True,
                },
                created_at=now,
                updated_at=now,
            )
            self.storage.add_node(node)
            knowledge_ids.append(node_id)

        return knowledge_ids

    # ------------------------------------------------------------------
    # 步骤5：语义边
    # ------------------------------------------------------------------

    def _build_semantic_edges(
        self,
        knowledge_ids: List[str],
        source_ids: List[str],
        entity_ids: List[str],
    ) -> int:
        """步骤5：建语义边

        创建两种边：
        - supports: knowledge → episodic（knowledge支持/源自哪些episodic）
        - about: knowledge → entity（knowledge关于哪个entity）

        Returns:
            创建的边数量
        """
        edge_count = 0

        for kid in knowledge_ids:
            # supports边：knowledge → 原始episodic
            for sid in source_ids:
                self.storage.add_edge(
                    kid,
                    sid,
                    EdgeTypes.SUPPORTS.value,
                    weight=0.8,
                )
                edge_count += 1

            # about边：knowledge → entity
            for eid in entity_ids:
                self.storage.add_edge(
                    kid,
                    eid,
                    EdgeTypes.ABOUT.value,
                    weight=0.9,
                )
                edge_count += 1

        return edge_count

    # ------------------------------------------------------------------
    # 步骤6：因果边
    # ------------------------------------------------------------------

    def _extract_causal_edges(
        self,
        group: List[MemoryNode],
        runtime_agent=None,
    ) -> int:
        """步骤6：提取因果边和entity间关系边（LLM）

        无LLM时基于情绪变化提取简单因果模式。
        有LLM时让LLM分析因果关系。

        Returns:
            创建的因果边数量
        """
        edge_count = 0

        # 如果有至少2条episodic且有LLM
        if (
            len(group) >= 2
            and runtime_agent is not None
            and hasattr(runtime_agent, "ask")
            and self._llm_calls_this_cycle < self._max_llm_calls
        ):
            try:
                prompt = self._build_causal_prompt(group)
                response = ask_memory_model(
                    runtime_agent,
                    prompt,
                    elfie_id=self.elfie_id,
                    config_dir=self.config_dir,
                    food_key="focus",
                    complexity=2,
                )
                self._llm_calls_this_cycle += 1
                if response and response.strip():
                    for line in response.strip().split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split("→")
                        if len(parts) == 2:
                            cause_id = parts[0].strip()
                            effect_id = parts[1].strip()
                            if cause_id.startswith("ep_") or effect_id.startswith(
                                "ep_"
                            ):
                                self.storage.add_edge(
                                    cause_id,
                                    effect_id,
                                    EdgeTypes.CAUSAL.value,
                                    weight=0.7,
                                )
                                edge_count += 1
            except Exception as e:
                logger.warning("LLM因果提取失败: %s，跳过步骤6", e)

        # LLM不可用时：基于情绪变化检测简单因果
        if edge_count == 0 and len(group) >= 2:
            for i in range(len(group) - 1):
                curr = group[i]
                next_ = group[i + 1]
                curr_emotion = curr.metadata.get("emotion", "")
                next_emotion = next_.metadata.get("emotion", "")
                if curr_emotion and next_emotion and curr_emotion != next_emotion:
                    self.storage.add_edge(
                        curr.id,
                        next_.id,
                        EdgeTypes.CAUSAL.value,
                        weight=0.5,
                    )
                    edge_count += 1

        return edge_count

    def _build_causal_prompt(self, group: List[MemoryNode]) -> str:
        """构建LLM因果提取提示"""
        episodes_text = "\n".join(
            f"[{n.id}] [{n.metadata.get('timestamp', 'unknown')}] "
            f"{n.content}（情绪:{n.metadata.get('emotion', '未知')}）"
            for n in group
        )
        return (
            "你是一个因果分析系统。以下是按时间排列的经历：\n"
            f"{episodes_text}\n\n"
            "请分析因果关系，每行输出一条因果：源节点ID → 目标节点ID\n"
            "只输出因果关系，每行一个。没有因果关系则不输出。\n"
        )

    # ------------------------------------------------------------------
    # 步骤7：实体属性更新
    # ------------------------------------------------------------------

    def _update_entity_properties(
        self,
        entity_id: str,
        entity_node: MemoryNode,
        knowledge_items: List[Dict[str, Any]],
        group: List[MemoryNode],
    ) -> None:
        """步骤7：更新entity属性

        将新发现的信息更新到entity.properties。
        保留历史版本（旧属性保存在metadata中），支持回滚。
        """
        # 提取情绪统计
        emotions = [
            n.metadata.get("emotion", "")
            for n in group
            if n.metadata.get("emotion", "")
        ]
        emotion_counts = dict(Counter(emotions))

        # 构建更新
        update_meta = {
            "consolidationInteractions": entity_node.metadata.get(
                "consolidationInteractions",
                0,
            )
            + len(group),
            "consolidationEmotions": emotion_counts,
            "knowledgeCount": entity_node.metadata.get(
                "knowledgeCount",
                0,
            )
            + len(knowledge_items),
            "lastConsolidatedAt": datetime.now(timezone.utc).isoformat(),
        }

        # 保存旧版本到metadata.backup（支持回滚）
        backup = entity_node.metadata.get("consolidationBackup")
        if backup is None:
            update_meta["consolidationBackup"] = {
                "interactions": entity_node.metadata.get(
                    "consolidationInteractions",
                    0,
                ),
                "knowledgeCount": entity_node.metadata.get("knowledgeCount", 0),
            }

        self.storage.update_node(entity_id, metadata=update_meta)

    # ------------------------------------------------------------------
    # 步骤8：标记
    # ------------------------------------------------------------------

    def _mark_consolidated(self, node_ids: List[str]) -> None:
        """步骤8：标记原始episodic为consolidated=True

        设置每个episodic节点的metadata.consolidated = True，
        并记录巩固时间戳。不物理删除任何节点。
        """
        for nid in set(node_ids):
            self.storage.update_node(
                nid,
                metadata={
                    "consolidated": True,
                    "consolidated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    # ------------------------------------------------------------------
    # 步骤7.5：Pattern发现
    # ------------------------------------------------------------------

    _STOP_CHARS = frozenset(
        "的了一是在有和就不人都到说要去你会着没看好自己"
        "这那什么怎么谁哪几多少时候地得以为对吧吗啊"
        "呢哦呀哈哇嗯嘿啦呗嘛"
    )

    def _discover_patterns(
        self, knowledge_ids: List[str], runtime_agent=None
    ) -> List[str]:
        """步骤7.5：从knowledge节点中发现pattern（更高层次的规律抽象）

        Pattern是比knowledge更高层的抽象：
        - knowledge: "主人每天8点喂我"（具体规律）
        - pattern: "固定时间=好事"（抽象信念）

        策略：
        1. 收集所有knowledge节点
        2. 至少需要2个knowledge节点才触发
        3. 优先用LLM发现共同模式（未超限时）
        4. LLM失败时降级为规则匹配（找共同关键词）
        5. 创建pattern节点（含pattern_confidence）
        6. 建implies边：knowledge → pattern

        Returns:
            创建的pattern节点ID列表
        """
        if len(knowledge_ids) < 2:
            return []

        # 收集所有knowledge节点
        knowledge_nodes = []
        for kid in knowledge_ids:
            node = self.storage.get_node(kid)
            if node:
                knowledge_nodes.append(node)

        if len(knowledge_nodes) < 2:
            return []

        patterns: List[Dict[str, Any]] = []

        # 优先用LLM发现共同模式
        if (
            runtime_agent is not None
            and hasattr(runtime_agent, "ask")
            and self._llm_calls_this_cycle < self._max_llm_calls
        ):
            try:
                prompt = self._build_pattern_prompt(knowledge_nodes)
                response = ask_memory_model(
                    runtime_agent,
                    prompt,
                    elfie_id=self.elfie_id,
                    config_dir=self.config_dir,
                    food_key="focus",
                    complexity=2,
                )
                self._llm_calls_this_cycle += 1
                if response and response.strip():
                    for line in response.strip().split("\n"):
                        line = line.strip().lstrip("-* ").strip()
                        if line and len(line) > 3:
                            patterns.append({"content": line, "confidence": 0.7})
            except Exception as e:
                logger.warning("LLM pattern发现失败: %s，降级为规则匹配", e)

        # LLM失败或不可用时降级为规则匹配
        if not patterns:
            patterns = self._rule_based_pattern_discovery(knowledge_nodes)

        if not patterns:
            return []

        # 创建pattern节点
        pattern_ids = self._create_pattern_nodes(patterns, knowledge_ids)

        # 建implies边
        self._build_pattern_edges(pattern_ids, knowledge_ids)

        if pattern_ids:
            logger.info(
                "Pattern发现：从%d个knowledge节点中发现%d个pattern",
                len(knowledge_ids),
                len(pattern_ids),
            )

        return pattern_ids

    def _build_pattern_prompt(self, knowledge_nodes: List[MemoryNode]) -> str:
        """构建LLM pattern发现提示"""
        knowledge_text = "\n".join(f"- {n.content}" for n in knowledge_nodes)
        return (
            "你是一个记忆抽象系统。以下是精灵小狐狸艾菲学到的知识：\n"
            f"{knowledge_text}\n\n"
            "请从中发现更高层次的抽象规律/信念，每行输出一条。\n"
            "这些规律应该是跨知识的通用模式，而非具体事实。\n"
            "示例：\n"
            "- 固定时间发生的事通常是好事\n"
            "- 主人的行为有规律性\n"
            "- 陌生环境需要谨慎\n"
        )

    def _rule_based_pattern_discovery(
        self, knowledge_nodes: List[MemoryNode]
    ) -> List[Dict[str, Any]]:
        """基于规则的模式发现（LLM不可用时的降级方案）

        提取所有knowledge节点的关键词，找到出现在多个knowledge中的
        共同关键词。如果有共同关键词，生成pattern描述。
        """
        patterns: List[Dict[str, Any]] = []

        # 提取每个knowledge节点的关键词（去重后）
        all_token_sets = []
        for node in knowledge_nodes:
            tokens = tokenize(node.content)
            meaningful = [t for t in tokens if t not in self._STOP_CHARS]
            all_token_sets.append(set(meaningful))

        if len(all_token_sets) < 2:
            return patterns

        # 找到出现在多个knowledge中的共同关键词
        token_counter: Counter = Counter()
        for token_set in all_token_sets:
            token_counter.update(token_set)

        common_keywords = [word for word, count in token_counter.items() if count >= 2]

        if common_keywords:
            keywords_str = "、".join(common_keywords[:3])
            patterns.append(
                {
                    "content": f"关于「{keywords_str}」的多个知识表明这是重要的模式",
                    "confidence": 0.6,
                }
            )

        return patterns

    def _create_pattern_nodes(
        self,
        patterns: List[Dict[str, Any]],
        source_knowledge_ids: List[str],
    ) -> List[str]:
        """创建PATTERN类型节点

        metadata包含：
        - pattern_confidence: 置信度
        - source_knowledge_ids: 来源knowledge节点ID列表
        - consolidation_round: 巩固轮次
        """
        pattern_ids: List[str] = []
        now = datetime.now(timezone.utc).isoformat()

        for item in patterns:
            self._pattern_counter += 1
            node_id = f"pattern_c{self._consolidation_count}_n{self._pattern_counter}"
            node = MemoryNode(
                id=node_id,
                type=NodeTypes.PATTERN.value,
                content=item["content"],
                metadata={
                    "pattern_confidence": item.get("confidence", 0.5),
                    "source_knowledge_ids": source_knowledge_ids,
                    "consolidation_round": self._consolidation_count,
                    "created_in_consolidation": True,
                },
                created_at=now,
                updated_at=now,
            )
            self.storage.add_node(node)
            pattern_ids.append(node_id)

        return pattern_ids

    def _build_pattern_edges(
        self, pattern_ids: List[str], knowledge_ids: List[str]
    ) -> int:
        """建implies边：knowledge → pattern

        每个knowledge节点都implies它来源的pattern节点。
        weight从pattern节点metadata的pattern_confidence获取。
        """
        edge_count = 0
        for pid in pattern_ids:
            pattern_node = self.storage.get_node(pid)
            weight = (
                pattern_node.metadata.get("pattern_confidence", 0.5)
                if pattern_node
                else 0.5
            )
            for kid in knowledge_ids:
                self.storage.add_edge(
                    kid,
                    pid,
                    EdgeTypes.IMPLIES.value,
                    weight=weight,
                )
                edge_count += 1
        return edge_count
