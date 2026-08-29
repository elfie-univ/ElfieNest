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

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, cast

from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationBatchReceipt,
    ConsolidationProjection,
    ConsolidationRequest,
    DescriptionInput,
    EvidenceInput,
    MentionInput,
    NodeInput,
)
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.model_food import MemoryModelPort, ask_memory_model
from elfie.brain.memory.node_types import EdgeTypes, MemoryNode, NodeTypes
from elfie.brain.memory.tokenizer import tokenize

logger = logging.getLogger("elfie.brain.memory.consolidation")


class MemoryProjectionDeferred(RuntimeError):
    """A source Episode must wait for a usable model proposal."""


class MemoryConsolidator:
    """巩固引擎：将episodic记忆提炼为knowledge和entity属性更新"""

    def __init__(
        self,
        storage: MemoryStorePort,
        self_narrative=None,
        elfie_id: str | None = None,
    ):
        self.storage = storage
        self.self_narrative = self_narrative
        self._consolidation_count = 0  # 巩固次数计数
        self._knowledge_counter = 0  # 知识节点ID计数器
        self._pattern_counter = 0  # pattern节点ID计数器
        self._llm_calls_this_cycle = 0
        self._max_llm_calls = 4
        self.elfie_id = elfie_id

    def run_consolidation(
        self,
        model_port: MemoryModelPort | None = None,
        *,
        max_episodes: int | None = None,
    ) -> Dict[str, Any]:
        """执行巩固流程（8.5步骤，含pattern发现）

        Steps:
        1-7: 同基础巩固流程
        7.5: 从knowledge节点中发现pattern，创建PATTERN节点，建implies边
        8:   标记consolidated

        Args:
            model_port: 可选LLM运行时代理，提供ask()接口

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

        # The target SQLite adapter exposes a source-first typed contract. Keep
        # the historical MemoryNode algorithm below for semantic Fakes and
        # third-party adapters that have not adopted that contract yet.
        if callable(getattr(self.storage, "claim_episodes", None)) and callable(
            getattr(self.storage, "apply_consolidation", None)
        ):
            return self._run_source_first(
                model_port=model_port,
                max_episodes=max_episodes,
            )

        # 步骤1：收集未巩固episodic节点
        episodic_nodes = self._collect_unconsolidated(limit=max_episodes)
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
                model_port,
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
                model_port,
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
            pattern_ids = self._discover_patterns(all_knowledge_ids, model_port)
            result["patterns_created"] = len(pattern_ids)

        # 步骤8：标记原始episodic为consolidated=True
        self._mark_consolidated(all_source_ids)

        self._consolidation_count += 1
        result["consolidated_count"] = len(set(all_source_ids))
        result["knowledge_created"] = len(all_knowledge_ids)

        # 核心认知更新
        if self.self_narrative is not None:
            try:
                self.self_narrative.update(
                    consolidation_results=result,
                    model_port=model_port,
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

    def _run_source_first(
        self,
        *,
        model_port: MemoryModelPort | None,
        max_episodes: int | None,
    ) -> Dict[str, Any]:
        limit = max_episodes if max_episodes is not None else 8
        if limit < 1:
            return {
                "consolidated_count": 0,
                "knowledge_created": 0,
                "edges_created": 0,
                "patterns_created": 0,
            }
        batch = self.run_batch(
            ConsolidationRequest(max_episodes=limit), model_port=model_port
        )
        result = {
            "consolidated_count": len(batch.consolidated_episode_ids),
            "knowledge_created": batch.nodes_created,
            "edges_created": batch.assertions_created,
            "patterns_created": 0,
        }
        return result

    def run_batch(
        self,
        request: ConsolidationRequest,
        *,
        model_port: MemoryModelPort | None = None,
    ) -> ConsolidationBatchReceipt:
        """Run one bounded, retryable consolidation worker pass.

        The target adapter claims source Episodes before any model call.  A
        failed proposal or transaction only marks that Episode retryable; it
        never discards the complete source.  Legacy adapters use the existing
        algorithm as a compatibility path and do not widen the target Port.
        """
        if not (
            callable(getattr(self.storage, "claim_episodes", None))
            and callable(getattr(self.storage, "apply_consolidation", None))
        ):
            pending = tuple(self.pending_episode_ids(request.max_episodes))
            result = self.run_consolidation(
                model_port=model_port, max_episodes=request.max_episodes
            )
            count = int(result.get("consolidated_count", 0))
            return ConsolidationBatchReceipt(
                worker_id=request.worker_id,
                requested=request.max_episodes,
                consolidated_episode_ids=pending[:count],
                nodes_created=int(result.get("knowledge_created", 0)),
                assertions_created=int(result.get("edges_created", 0)),
                checkpoint=request.checkpoint,
            )

        recover = getattr(self.storage, "recover_expired_leases", None)
        if callable(recover):
            # Recovery is part of every bounded worker pass.  A crashed worker
            # must not require a separate scheduler tick before its Episodes
            # become eligible again.
            recover()

        episodes = self.storage.claim_episodes(
            limit=request.max_episodes,
            owner=request.worker_id,
            lease_seconds=request.lease_seconds,
        )
        consolidated: list[str] = []
        failed: list[str] = []
        errors: dict[str, str] = {}
        nodes_created = 0
        assertions_created = 0
        evidence_created = 0
        for episode in episodes:
            try:
                projection = self._projection_for_episode(
                    episode,
                    model_port,
                    allow_deterministic_fallback=False,
                )
                receipt = self.storage.apply_consolidation(projection)
                consolidated.append(episode.episode_id)
                nodes_created += receipt.nodes_created
                assertions_created += receipt.assertions_created
                evidence_created += receipt.evidence_created
            except Exception as error:  # noqa: BLE001 - retryable worker boundary
                message = str(error)
                logger.warning("Episode consolidation failed: %s", error)
                claim_owner, claim_attempt = _episode_claim(episode)
                self.storage.mark_episode_failed(
                    episode.episode_id,
                    message,
                    owner=claim_owner,
                    attempt=claim_attempt,
                )
                failed.append(episode.episode_id)
                errors[episode.episode_id] = message
        if consolidated and self.self_narrative is not None:
            try:
                self.self_narrative.update(
                    consolidation_results={
                        "consolidated_count": len(consolidated),
                        "knowledge_created": nodes_created,
                        "edges_created": assertions_created,
                        "patterns_created": 0,
                    },
                    model_port=model_port,
                )
            except Exception as error:
                logger.error("核心认知更新失败: %s", error)
        return ConsolidationBatchReceipt(
            worker_id=request.worker_id,
            requested=request.max_episodes,
            consolidated_episode_ids=tuple(consolidated),
            failed_episode_ids=tuple(failed),
            nodes_created=nodes_created,
            assertions_created=assertions_created,
            evidence_created=evidence_created,
            checkpoint=request.checkpoint,
            errors=errors,
        )

    def pending_episode_ids(self, limit: int) -> tuple[str, ...]:
        """Return IDs for the compatibility batch receipt without SQL access."""
        if limit < 1:
            return ()
        if callable(getattr(self.storage, "pending_episodes", None)):
            return tuple(
                episode.episode_id
                for episode in self.storage.pending_episodes(limit=limit)
            )
        return tuple(node.id for node in self._collect_unconsolidated(limit=limit))

    def _projection_for_episode(
        self,
        episode: ClosedEpisode,
        model_port: MemoryModelPort | None,
        *,
        allow_deterministic_fallback: bool = True,
    ) -> ConsolidationProjection:
        evidence_id = f"evidence:{episode.episode_id}"
        evidence = EvidenceInput(
            evidence_id=evidence_id,
            source_type="episode",
            source_id=episode.episode_id,
            excerpt=episode.content_text,
            modality="text",
            captured_at=episode.occurred_from,
            source_sha256=episode.content_sha256
            or hashlib.sha256(episode.content_text.encode("utf-8")).hexdigest(),
            source_version=episode.source_version,
            attribution=episode.attribution,
        )
        event_id = f"event:{episode.episode_id}"
        nodes: list[NodeInput] = [
            NodeInput(
                node_id=event_id,
                node_type="event",
                canonical_label=episode.summary_text or episode.content_text[:120],
                description=episode.content_text,
                confidence=1.0,
                properties={"episode_id": episode.episode_id},
            )
        ]
        mentions: list[MentionInput] = [
            MentionInput(
                episode_id=episode.episode_id,
                surface_text=episode.summary_text or episode.content_text[:120],
                node_id=event_id,
                resolution_state="resolved",
                role="event",
                confidence=1.0,
            )
        ]
        model_projection = self._projection_from_model(
            episode=episode,
            model_port=model_port,
            evidence_id=evidence_id,
            event_id=event_id,
            evidence=evidence,
            base_nodes=nodes,
            base_mentions=mentions,
            required=not allow_deterministic_fallback,
        )
        if model_projection is not None:
            claim_owner, claim_attempt = _episode_claim(episode)
            return replace(
                model_projection,
                claim_owner=claim_owner,
                claim_attempt=claim_attempt,
            )

        assertions: list[AssertionInput] = []
        aliases: list[AliasInput] = []
        labels = self._labels_from_content(episode.content_text)
        label_nodes: list[tuple[str, str]] = []
        for label, node_type, start in labels:
            node_id = (
                "node:"
                + hashlib.sha256(
                    f"elfie|{node_type}|{label.casefold()}".encode()
                ).hexdigest()[:24]
            )
            label_nodes.append((label, node_id))
            nodes.append(
                NodeInput(
                    node_id=node_id,
                    node_type=node_type,
                    canonical_label=label,
                    confidence=0.75,
                )
            )
            mentions.append(
                MentionInput(
                    episode_id=episode.episode_id,
                    surface_text=label,
                    node_id=node_id,
                    resolution_state="resolved",
                    role=node_type,
                    span_start=start,
                    span_end=start + len(label),
                    confidence=0.75,
                )
            )
            assertions.append(
                AssertionInput(
                    subject_id=event_id,
                    predicate="involves",
                    object_node_id=node_id,
                    confidence=0.8,
                    support_score=0.8,
                    evidence_ids=(evidence_id,),
                )
            )
        self._append_deterministic_owner_claims(
            episode.content_text,
            episode.episode_id,
            evidence_id,
            nodes,
            mentions,
            assertions,
        )
        self._append_deterministic_entity_facts(
            episode.content_text,
            episode.episode_id,
            evidence_id,
            nodes,
            aliases,
            mentions,
            assertions,
        )
        if episode.emotion:
            emotion_id = (
                "emotion:"
                + hashlib.sha256(
                    episode.emotion.casefold().encode("utf-8")
                ).hexdigest()[:24]
            )
            nodes.append(
                NodeInput(
                    node_id=emotion_id,
                    node_type="emotion",
                    canonical_label=episode.emotion,
                    confidence=0.8,
                )
            )
            assertions.append(
                AssertionInput(
                    subject_id=event_id,
                    predicate="felt",
                    object_node_id=emotion_id,
                    confidence=0.8,
                    support_score=0.7,
                    evidence_ids=(evidence_id,),
                )
            )
        # Capture a small, explicit social/affinity fact when the wording is
        # unambiguous. The source Episode remains the complete narrative.
        if any(token in episode.content_text for token in ("喜欢", "爱", "讨厌")):
            relation = "dislikes" if "讨厌" in episode.content_text else "likes"
            if len(label_nodes) >= 2:
                assertions.append(
                    AssertionInput(
                        subject_id=label_nodes[0][1],
                        predicate=relation,
                        object_node_id=label_nodes[1][1],
                        confidence=0.65,
                        support_score=0.6,
                        evidence_ids=(evidence_id,),
                    )
                )
        return ConsolidationProjection(
            episode_id=episode.episode_id,
            nodes=tuple(nodes),
            aliases=tuple(aliases),
            mentions=tuple(mentions),
            assertions=tuple(assertions),
            evidence=(evidence,),
            source_version=episode.source_version,
            source_sha256=episode.content_sha256
            or hashlib.sha256(episode.content_text.encode("utf-8")).hexdigest(),
            claim_owner=_episode_claim(episode)[0],
            claim_attempt=_episode_claim(episode)[1],
        )

    @staticmethod
    def _append_deterministic_owner_claims(
        content: str,
        episode_id: str,
        evidence_id: str,
        nodes: list[NodeInput],
        mentions: list[MentionInput],
        assertions: list[AssertionInput],
    ) -> None:
        """Extract only explicit, source-grounded owner facts.

        This deliberately handles a small set of unambiguous Chinese/English
        forms.  It is a safety fallback, not a semantic parser: every value is
        copied from the Episode and remains attributed to the speaker.
        """
        owner_patterns = (
            "我叫",
            "叫我",
            "我的名字",
            "我喜欢",
            "我不喜欢",
            "我讨厌",
            "不叫",
            "改成",
            "改名",
            "我有个",
            "我的朋友",
        )
        if not any(marker in content for marker in owner_patterns):
            return
        owner_id = _projection_id("node:", "person", "elfie", "主人")
        if not any(node.node_id == owner_id for node in nodes):
            nodes.append(
                NodeInput(
                    node_id=owner_id,
                    node_type="person",
                    canonical_label="主人",
                    confidence=1.0,
                    properties={"attribution": "owner"},
                )
            )
        correction = any(
            marker in content for marker in ("不叫", "不是", "更喜欢", "纠正", "改成")
        )

        def add_claim(predicate: str, value: str, start: int) -> None:
            value = value.strip().strip("，。！？,.!?；;")
            if not value or len(value) > 64:
                return
            assertions.append(
                AssertionInput(
                    subject_id=owner_id,
                    predicate=predicate,
                    object_literal=value,
                    epistemic_status="reported",
                    viewpoint="owner",
                    context="correction" if correction else "owner_claim",
                    confidence=0.95,
                    support_score=0.95,
                    evidence_ids=(evidence_id,),
                    assertion_id=_projection_id("claim:", episode_id, predicate, value),
                )
            )
            mentions.append(
                MentionInput(
                    episode_id=episode_id,
                    surface_text=value,
                    resolution_state="unresolved",
                    role="owner_claim_value",
                    span_start=start,
                    span_end=start + len(value),
                    confidence=0.95,
                )
            )

        patterns = (
            (
                "preferred_name",
                r"(?:我|主人)\s*(?:不叫|不是)\s*[^\s，。！？,.!?；;]+(?:了)?"
                r"\s*[，,]\s*(?:(?:我|主人)\s*)?(?:叫|改成|现在叫)\s*"
                r"([^\s，。！？,.!?；;]+)",
            ),
            (
                "preferred_name",
                r"(?:我|主人)\s*(?:改成|改名为|改名叫|现在叫)\s*"
                r"([^\s，。！？,.!?；;]+)",
            ),
            (
                "preferred_name",
                r"(?:我|主人)\s*(?:的名字是|叫做|叫|名叫)\s*([^\s，。！？,.!?；;]+)",
            ),
            ("preferred_name", r"叫我\s*([^\s，。！？,.!?；;]+)"),
            (
                "likes",
                r"(?:我|主人)\s*(?:喜欢|爱吃|爱|更喜欢)\s*([^\s，。！？,.!?；;]+)",
            ),
            ("dislikes", r"(?:我|主人)\s*(?:不喜欢|讨厌)\s*([^\s，。！？,.!?；;]+)"),
        )
        for predicate, pattern in patterns:
            match = re.search(pattern, content, flags=re.IGNORECASE)
            if match is not None:
                add_claim(predicate, match.group(1), match.start(1))

    @staticmethod
    def _append_deterministic_entity_facts(
        content: str,
        episode_id: str,
        evidence_id: str,
        nodes: list[NodeInput],
        aliases: list[AliasInput],
        mentions: list[MentionInput],
        assertions: list[AssertionInput],
    ) -> None:
        """Capture explicitly named people, aliases and relationships."""
        matches = list(
            re.finditer(
                r"(?:我的|我有个|那个)?(?:朋友|同事|同学|哥哥|姐姐|弟弟|妹妹|爸爸|妈妈)"
                r"\s*(?:叫|名字是|名叫|是)\s*([^\s，。！？,.!?；;]+)",
                content,
            )
        )
        for match in matches:
            label = match.group(1).strip()
            if not label or len(label) > 32:
                continue
            node_id = _projection_id("node:", "person", "elfie", label)
            if not any(node.node_id == node_id for node in nodes):
                nodes.append(
                    NodeInput(
                        node_id=node_id,
                        node_type="person",
                        canonical_label=label,
                        confidence=0.9,
                    )
                )
            mentions.append(
                MentionInput(
                    episode_id=episode_id,
                    surface_text=label,
                    node_id=node_id,
                    resolution_state="resolved",
                    role="person",
                    span_start=match.start(1),
                    span_end=match.end(1),
                    confidence=0.9,
                )
            )
            owner_id = _projection_id("node:", "person", "elfie", "主人")
            if any(node.node_id == owner_id for node in nodes):
                assertions.append(
                    AssertionInput(
                        subject_id=owner_id,
                        predicate="knows",
                        object_node_id=node_id,
                        viewpoint="owner",
                        epistemic_status="reported",
                        confidence=0.85,
                        support_score=0.85,
                        evidence_ids=(evidence_id,),
                    )
                )
        for match in re.finditer(
            r"([^\s，。！？,.!?；;]{1,32})\s*(?:也叫|又叫|昵称是)\s*([^\s，。！？,.!?；;]{1,32})",
            content,
        ):
            canonical, alias = (value.strip() for value in match.groups())
            node_id = _projection_id("node:", "person", "elfie", canonical)
            if any(node.node_id == node_id for node in nodes):
                aliases.append(
                    AliasInput(
                        node_id=node_id,
                        alias=alias,
                        evidence_id=evidence_id,
                        confidence=0.9,
                    )
                )

    def _projection_from_model(
        self,
        *,
        episode: ClosedEpisode,
        model_port: MemoryModelPort | None,
        evidence_id: str,
        event_id: str,
        evidence: EvidenceInput,
        base_nodes: list[NodeInput],
        base_mentions: list[MentionInput],
        required: bool = False,
    ) -> ConsolidationProjection | None:
        """Validate an optional model proposal before it reaches SQLite.

        The model is only a bounded candidate producer.  Every promoted label
        must occur in the complete Episode, every assertion is grounded in the
        Episode evidence, and deterministic IDs are derived from the Episode
        rather than from model output.  Legacy callers may opt into the
        conservative local extractor; the source-first target path marks an
        absent or invalid proposal retryable instead.
        """
        if model_port is None or not callable(
            getattr(model_port, "ask_with_food", None)
        ):
            if required:
                raise MemoryProjectionDeferred(
                    "memory consolidation requires an injected model"
                )
            return None
        prompt = (
            "从下面这条已经闭合的 Elfie Episode 提取候选记忆。只能返回 JSON 对象，"
            "不要 Markdown。所有 nodes.label、mentions.surface_text、assertions 的"
            "subject_ref/object_ref 必须是原文中出现的短语；不要补写原文没有的事实。"
            "结构：{nodes:[{label,type,description,aliases}],mentions:[{surface_text,label,role}],"
            "assertions:[{subject_ref,predicate,object_ref,object_literal,polarity,"
            "epistemic_status,viewpoint,context,confidence,support_score}]}\n"
            f"Episode：{episode.content_text}"
        )
        try:
            response = ask_memory_model(
                model_port,
                prompt,
                elfie_id=self.elfie_id,
                semantic_role="memory_consolidation",
                complexity=2,
            )
            raw = _parse_json_object(response)
            return self._validate_model_projection(
                episode=episode,
                raw=raw,
                evidence=evidence,
                evidence_id=evidence_id,
                event_id=event_id,
                base_nodes=base_nodes,
                base_mentions=base_mentions,
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            logger.warning("模型记忆提案无效: %s", error)
            if required:
                raise MemoryProjectionDeferred(
                    "memory model proposal did not satisfy the grounded contract"
                ) from error
            return None
        except Exception as error:  # noqa: BLE001 - model failures are retryable
            # A provider outage is different from an ungrounded proposal.  Do
            # not mark the source Episode consolidated with guessed facts; the
            # worker will lease it again after the retry backoff.
            logger.warning("模型记忆提案调用失败，保留 Episode 等待重试: %s", error)
            raise RuntimeError("memory model proposal failed") from error

    def _validate_model_projection(
        self,
        *,
        episode: ClosedEpisode,
        raw: Mapping[str, Any],
        evidence: EvidenceInput,
        evidence_id: str,
        event_id: str,
        base_nodes: list[NodeInput],
        base_mentions: list[MentionInput],
    ) -> ConsolidationProjection | None:
        content = episode.content_text
        nodes = list(base_nodes)
        mentions = list(base_mentions)
        aliases: list[Any] = []
        descriptions: list[Any] = []
        labels_to_ids: dict[str, str] = {}
        raw_nodes = raw.get("nodes", ())
        if not isinstance(raw_nodes, list):
            raise ValueError("nodes must be a list")
        for item in raw_nodes:
            if not isinstance(item, dict):
                raise ValueError("node proposal must be an object")
            label = _required_model_text(item, "label")
            if label not in content:
                raise ValueError("model node label is not grounded in Episode")
            node_type = _model_text(item.get("type")) or "concept"
            # Reusable semantic anchors share identity across Episodes.  Event
            # nodes remain episode-scoped; the adapter also resolves aliases
            # deterministically when a proposal uses a different local ID.
            node_id = _projection_id("node:", node_type, "elfie", label)
            labels_to_ids[label] = node_id
            raw_description = _model_text(item.get("description"))
            grounded_description = (
                raw_description
                if raw_description and raw_description in content
                else None
            )
            nodes.append(
                NodeInput(
                    node_id=node_id,
                    node_type=node_type,
                    canonical_label=label,
                    description=grounded_description,
                    confidence=_model_score(item.get("confidence"), 0.6),
                )
            )
            raw_aliases = item.get("aliases", [])
            if raw_aliases is not None:
                if not isinstance(raw_aliases, list):
                    raise ValueError("aliases must be a list")
                for alias_value in raw_aliases:
                    alias = str(alias_value).strip()
                    if alias and alias in content:
                        aliases.append(
                            _alias_input(
                                node_id=node_id,
                                alias=alias,
                                evidence_id=evidence_id,
                                confidence=_model_score(item.get("confidence"), 0.6),
                            )
                        )
            if grounded_description:
                description = grounded_description
                if description and description in content:
                    descriptions.append(
                        _description_input(
                            node_id=node_id,
                            text=description,
                            evidence_id=evidence_id,
                            confidence=_model_score(item.get("confidence"), 0.6),
                        )
                    )
        raw_mentions = raw.get("mentions", [])
        if not isinstance(raw_mentions, list):
            raise ValueError("mentions must be a list")
        for item in raw_mentions:
            if not isinstance(item, dict):
                raise ValueError("mention proposal must be an object")
            surface = _required_model_text(item, "surface_text")
            if surface not in content:
                raise ValueError("model mention is not grounded in Episode")
            label = _model_text(item.get("label")) or surface
            resolved_node_id = labels_to_ids.get(label)
            if resolved_node_id is None:
                resolved_node_id = _projection_id("node:", "concept", "elfie", label)
                labels_to_ids[label] = resolved_node_id
                nodes.append(
                    NodeInput(resolved_node_id, "concept", label, confidence=0.55)
                )
            start = _model_int(item.get("span_start"))
            if start is None:
                start = content.find(surface)
            mentions.append(
                MentionInput(
                    episode_id=episode.episode_id,
                    surface_text=surface,
                    node_id=resolved_node_id,
                    resolution_state="resolved",
                    role=_model_text(item.get("role")),
                    span_start=start if start >= 0 else None,
                    span_end=(start + len(surface)) if start >= 0 else None,
                    confidence=_model_score(item.get("confidence"), 0.6),
                )
            )

        assertions: list[AssertionInput] = []
        raw_assertions = raw.get("assertions", [])
        if not isinstance(raw_assertions, list):
            raise ValueError("assertions must be a list")
        for item in raw_assertions:
            if not isinstance(item, dict):
                raise ValueError("assertion proposal must be an object")
            subject_ref = _required_model_text(item, "subject_ref")
            if subject_ref not in labels_to_ids:
                raise ValueError("assertion subject is not a proposed node")
            object_ref = _model_text(item.get("object_ref"))
            object_literal = item.get("object_literal")
            if object_ref is None and object_literal is None:
                raise ValueError("assertion needs object_ref or object_literal")
            if object_ref is not None:
                if object_ref not in labels_to_ids:
                    raise ValueError("assertion object is not a proposed node")
                object_node_id = labels_to_ids[object_ref]
            else:
                object_node_id = None
            predicate = _required_model_text(item, "predicate")
            assertions.append(
                AssertionInput(
                    subject_id=labels_to_ids[subject_ref],
                    predicate=predicate,
                    object_node_id=object_node_id,
                    object_literal=object_literal,
                    object_unit=_model_text(item.get("object_unit")),
                    polarity=cast(
                        Literal["positive", "negative"],
                        _model_enum(
                            item.get("polarity"), {"positive", "negative"}, "positive"
                        ),
                    ),
                    epistemic_status=cast(
                        Literal["known", "believed", "uncertain", "reported"],
                        _model_enum(
                            item.get("epistemic_status"),
                            {"known", "believed", "uncertain", "reported"},
                            "known",
                        ),
                    ),
                    viewpoint=_model_text(item.get("viewpoint")),
                    context=_model_text(item.get("context")),
                    confidence=_model_score(item.get("confidence"), 0.6),
                    support_score=_model_score(item.get("support_score"), 0.6),
                    importance=_model_score(
                        item.get("importance", item.get("support_score")), 0.6
                    ),
                    object_literal_type=_model_text(item.get("object_literal_type")),
                    evidence_ids=(evidence_id,),
                )
            )
        if not assertions and len(nodes) == len(base_nodes):
            return None
        return ConsolidationProjection(
            episode_id=episode.episode_id,
            nodes=tuple(nodes),
            aliases=tuple(aliases),
            descriptions=tuple(descriptions),
            mentions=tuple(mentions),
            assertions=tuple(assertions),
            evidence=(evidence,),
            extraction_run_id="model:"
            + hashlib.sha256(episode.content_text.encode("utf-8")).hexdigest()[:16],
            source_version=episode.source_version,
            source_sha256=episode.content_sha256,
        )

    @staticmethod
    def _labels_from_content(content: str) -> list[tuple[str, str, int]]:
        dictionary = {
            "主人": "person",
            "朋友": "person",
            "长老": "person",
            "地球": "place",
            "精灵巢": "place",
            "花园": "place",
            "厨房": "place",
            "香菜": "food",
            "鱼味": "food",
            "鸡肉": "food",
            "猫": "animal",
            "狗": "animal",
            "牛顿第一定律": "knowledge",
            "万有引力": "knowledge",
        }
        found: list[tuple[str, str, int]] = []
        for label, kind in dictionary.items():
            start = content.find(label)
            if start >= 0:
                found.append((label, kind, start))
        # Quoted/marked terms are useful for seed knowledge while avoiding a
        # graph node for every token in ordinary prose.
        for match in re.finditer(r"[“「『]([^”」』]{2,32})[”」』]", content):
            label = match.group(1).strip()
            if label and not any(item[0] == label for item in found):
                found.append((label, "knowledge", match.start(1)))
        return sorted(found, key=lambda item: (item[2], item[0]))

    # ------------------------------------------------------------------
    # 步骤1：收集
    # ------------------------------------------------------------------

    def _collect_unconsolidated(self, limit: int | None = None) -> List[MemoryNode]:
        """步骤1：收集未巩固episodic节点"""
        nodes = self.storage.get_unconsolidated_nodes(node_type="episodic")
        return nodes if limit is None else nodes[: max(0, limit)]

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
        model_port: MemoryModelPort | None = None,
    ) -> List[Dict[str, Any]]:
        """步骤3：LLM知识提炼（降级为规则提取如果LLM不可用）

        优先使用LLM进行知识提取（每巩固周期≤4次调用）。
        LLM失败或不可用时降级为基于规则的提取。

        Returns:
            [{"content": str, "type": str, "confidence": float}, ...]
        """
        if model_port is not None and self._llm_calls_this_cycle < self._max_llm_calls:
            try:
                prompt = self._build_extraction_prompt(group, entity_name)
                response = ask_memory_model(
                    model_port,
                    prompt,
                    elfie_id=self.elfie_id,
                    semantic_role="reasoning",
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
        model_port: MemoryModelPort | None = None,
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
            and model_port is not None
            and self._llm_calls_this_cycle < self._max_llm_calls
        ):
            try:
                prompt = self._build_causal_prompt(group)
                response = ask_memory_model(
                    model_port,
                    prompt,
                    elfie_id=self.elfie_id,
                    semantic_role="reasoning",
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
        self,
        knowledge_ids: List[str],
        model_port: MemoryModelPort | None = None,
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
        if model_port is not None and self._llm_calls_this_cycle < self._max_llm_calls:
            try:
                prompt = self._build_pattern_prompt(knowledge_nodes)
                response = ask_memory_model(
                    model_port,
                    prompt,
                    elfie_id=self.elfie_id,
                    semantic_role="reasoning",
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


def _episode_claim(episode: ClosedEpisode) -> tuple[str | None, int | None]:
    """Read the storage-issued Episode claim token, if this is a claimed row."""
    owner_value = episode.metadata.get("_memory_claim_owner")
    attempt_value = episode.metadata.get("_memory_claim_attempt")
    owner = str(owner_value).strip() if owner_value is not None else ""
    attempt = _model_int(attempt_value)
    if not owner or attempt is None or attempt < 1:
        return None, None
    return owner, attempt


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model proposal must be a JSON object")
    return parsed


def _required_model_text(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    text = str(value).strip() if isinstance(value, str) else ""
    if not text:
        raise ValueError(f"model proposal field {key} must be non-blank")
    return text


def _model_text(value: object) -> str | None:
    text = str(value).strip() if isinstance(value, str) else ""
    return text or None


def _model_score(value: object, default: float) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if score > 1.0:
        score /= 100.0
    return max(0.0, min(1.0, score))


def _model_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, (float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _model_enum(value: object, allowed: set[str], default: str) -> str:
    text = _model_text(value)
    return text if text in allowed else default


def _projection_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _alias_input(
    *, node_id: str, alias: str, evidence_id: str, confidence: float
) -> AliasInput:
    return AliasInput(
        node_id=node_id,
        alias=alias,
        evidence_id=evidence_id,
        confidence=confidence,
    )


def _description_input(
    *, node_id: str, text: str, evidence_id: str, confidence: float
) -> DescriptionInput:
    return DescriptionInput(
        node_id=node_id,
        text=text,
        evidence_id=evidence_id,
        confidence=confidence,
    )
