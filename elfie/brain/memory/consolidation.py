"""Source-first Episode consolidation.

Each bounded worker claims complete Episodes, asks the injected model for a
grounded typed projection, and commits that projection with its source and
evidence in one retryable transaction.  A valid empty proposal may be
supplemented by the conservative local extractor; an invalid proposal or
provider failure leaves the source Episode retryable rather than silently
marking it consolidated.  Lifecycle, not consolidation, owns decay and
forgetting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import replace
from typing import Any, Dict, Literal, Mapping, cast

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
    memory_knowledge_kind,
    resolve_memory_node_type,
)
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.model_food import MemoryModelPort, ask_memory_model
from elfie.brain.memory.predicates import (
    NON_SEMANTIC_LEGACY_PREDICATES,
    relation_context,
    relation_importance,
    relation_spec,
    resolve_predicate,
)

logger = logging.getLogger("elfie.brain.memory.consolidation")

# A knowledge Node is a reusable index entry, not a second copy of the
# Episode.  Keep the admission rule close to the model boundary so a provider
# cannot turn a complete paragraph into the graph label shown by the UI.
_KNOWLEDGE_TITLE_MAX_CHARS = 40
_KNOWLEDGE_TITLE_SENTENCE_MARKS = frozenset("。！？!?；;\n")


class MemoryProjectionDeferred(RuntimeError):
    """A source Episode must wait for a usable model proposal."""


class MemoryConsolidator:
    """巩固引擎：将episodic记忆提炼为knowledge和entity属性更新"""

    def __init__(
        self,
        storage: MemoryStorePort,
        elfie_id: str | None = None,
    ):
        self.storage = storage
        self._llm_calls_this_cycle = 0
        self.elfie_id = elfie_id

    def run_consolidation(
        self,
        model_port: MemoryModelPort | None = None,
        *,
        max_episodes: int | None = None,
    ) -> Dict[str, Any]:
        """Run one bounded source-first consolidation pass.

        ``model_port`` is required for a worker pass so provider failures are
        visible and retryable; the source Episode is never discarded.
        """
        self._llm_calls_this_cycle = 0
        return self._run_source_first(
            model_port=model_port,
            max_episodes=max_episodes,
        )

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
        never discards the complete source.
        """
        self.storage.recover_expired_leases()

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

    def _projection_for_episode(
        self,
        episode: ClosedEpisode,
        model_port: MemoryModelPort | None,
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
        # Episodes are already the durable source unit.  Do not manufacture an
        # event Node for every Episode; only an explicit, reusable event
        # proposal may enter the graph below.
        nodes: list[NodeInput] = []
        mentions: list[MentionInput] = []
        model_projection = self._projection_from_model(
            episode=episode,
            model_port=model_port,
            evidence_id=evidence_id,
            evidence=evidence,
            base_nodes=nodes,
            base_mentions=mentions,
            required=True,
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
        for label, node_type, start in labels:
            node_id = (
                "node:"
                + hashlib.sha256(
                    f"elfie|{node_type}|{label.casefold()}".encode()
                ).hexdigest()[:24]
            )
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
            scope=(f"elfie:{self.elfie_id}" if self.elfie_id else "elfie"),
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
        forms.  It is a conservative local extractor, not a semantic parser:
        every value is copied from the Episode and remains attributed to the
        speaker.
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
                    importance=0.9,
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
        *,
        scope: str = "elfie",
    ) -> None:
        """Capture explicitly named entities, aliases and relationships.

        Pairwise social relations are admitted only when the Episode states the
        relation directly (for example ``Nemi 和 Pela 是朋友``).  Merely
        mentioning two names in one Episode is not enough to create an edge.
        ``elfie`` is used for named residents so the relation graph preserves
        the distinction between an Elfie and a human person.
        """
        name_pattern = r"(?:[A-Za-z][A-Za-z0-9_-]{0,31}|[\u4e00-\u9fff]{1,12})"
        pairwise_pattern = re.compile(
            rf"(?P<left>{name_pattern})\s*(?:和|与)\s*"
            rf"(?:精灵\s*)?(?P<right>{name_pattern})\s*"
            r"(?:是|属于)\s*(?P<role>朋友|家人|亲人|亲戚|同学|同事|邻居|玩伴|青梅竹马|兄弟姐妹|兄弟|姐妹)"
        )
        directed_pattern = re.compile(
            rf"(?P<subject>{name_pattern})\s*(?:是|属于)\s*"
            rf"(?P<object>{name_pattern})\s*的"
            r"(?P<role>父亲|母亲|爸爸|妈妈|父母|儿子|女儿|子女)"
        )
        relation_predicates = {
            "朋友": ("friend_of", "friend"),
            "玩伴": ("friend_of", "childhood_companion"),
            "青梅竹马": ("friend_of", "childhood_companion"),
            "家人": ("kin_of", "unspecified"),
            "亲人": ("kin_of", "unspecified"),
            "亲戚": ("kin_of", "unspecified"),
            "同学": ("classmate_of", "classmate"),
            "同事": ("colleague_of", "colleague"),
            "邻居": ("neighbor_of", "neighbor"),
            "兄弟姐妹": ("sibling_of", "sibling"),
            "兄弟": ("sibling_of", "sibling"),
            "姐妹": ("sibling_of", "sibling"),
        }
        directed_predicates = {
            "父亲": ("parent_of", "father"),
            "母亲": ("parent_of", "mother"),
            "爸爸": ("parent_of", "father"),
            "妈妈": ("parent_of", "mother"),
            "父母": ("parent_of", "unspecified"),
            "儿子": ("child_of", "son"),
            "女儿": ("child_of", "daughter"),
            "子女": ("child_of", "unspecified"),
        }
        emitted_assertions: set[str] = set()

        def add_elfie(label: str, start: int) -> str:
            node_id = _projection_id("node:", "elfie", "elfie", label)
            if not any(node.node_id == node_id for node in nodes):
                nodes.append(
                    NodeInput(
                        node_id=node_id,
                        node_type="elfie",
                        canonical_label=label,
                        scope=scope,
                        confidence=0.95,
                        properties={"extraction": "explicit_pairwise_relation"},
                    )
                )
            mentions.append(
                MentionInput(
                    episode_id=episode_id,
                    surface_text=label,
                    node_id=node_id,
                    resolution_state="resolved",
                    role="elfie",
                    span_start=start,
                    span_end=start + len(label),
                    confidence=0.95,
                )
            )
            return node_id

        def emit_relation(
            left: str,
            right: str,
            left_start: int,
            right_start: int,
            predicate: str,
            specificity: str,
            role: str,
            *,
            symmetric: bool,
            source: str,
        ) -> None:
            left_id = add_elfie(left, left_start)
            right_id = add_elfie(right, right_start)
            if symmetric:
                subject_id, object_id = sorted((left_id, right_id))
                assertion_id = _projection_id(
                    "assertion:",
                    episode_id,
                    predicate,
                    min(left_id, right_id),
                    max(left_id, right_id),
                )
            else:
                subject_id, object_id = left_id, right_id
                assertion_id = _projection_id(
                    "assertion:", episode_id, predicate, subject_id, object_id
                )
            if assertion_id in emitted_assertions:
                return
            emitted_assertions.add(assertion_id)
            assertions.append(
                AssertionInput(
                    subject_id=subject_id,
                    predicate=predicate,
                    object_node_id=object_id,
                    epistemic_status="reported",
                    context=relation_context(
                        source,
                        symmetric=symmetric,
                        specificity=specificity,
                        role=role,
                    ),
                    confidence=0.95,
                    importance=relation_importance(
                        predicate,
                        0.94 if specificity == "childhood_companion" else None,
                    ),
                    evidence_ids=(evidence_id,),
                    assertion_id=assertion_id,
                )
            )

        for match in pairwise_pattern.finditer(content):
            left = match.group("left").strip()
            right = match.group("right").strip()
            predicate, specificity = relation_predicates[match.group("role")]
            emit_relation(
                left,
                right,
                match.start("left"),
                match.start("right"),
                predicate,
                specificity,
                match.group("role"),
                symmetric=True,
                source="explicit_pairwise_relation",
            )

        for match in directed_pattern.finditer(content):
            predicate, specificity = directed_predicates[match.group("role")]
            emit_relation(
                match.group("subject").strip(),
                match.group("object").strip(),
                match.start("subject"),
                match.start("object"),
                predicate,
                specificity,
                match.group("role"),
                symmetric=False,
                source="explicit_directed_relation",
            )

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
        evidence: EvidenceInput,
        base_nodes: list[NodeInput],
        base_mentions: list[MentionInput],
        required: bool = False,
    ) -> ConsolidationProjection | None:
        """Validate an optional model proposal before it reaches SQLite.

        The model is only a bounded candidate producer.  Every promoted label
        must occur in the complete Episode, every assertion is grounded in the
        Episode evidence, and deterministic IDs are derived from the Episode
        rather than from model output.  A valid empty proposal may be
        supplemented by the conservative local extractor; an absent or
        invalid proposal remains retryable instead.
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
            "不要 Markdown。所有节点标题、mentions.surface_text、assertions 的"
            "subject_ref/object_ref 必须是原文中出现的短语；不要补写原文没有的事实。"
            "knowledge 节点必须提供唯一的短标题 title（不超过40字，不能是完整句子），"
            "并把完整解释放在 context，且只有可复用知识才设置 reusable_knowledge:true；"
            "普通事实只保留在 Episode。旧格式也可用 label 作为短标题，但完整句子不能作为标题。"
            "不要为每条 Episode 自动创建 event 节点；只有可被其他记录复用的明确事件才可将"
            "type设为event并同时给出reusable_event:true。不要生成about、knows、knows_boundary或related_to。"
            "结构：{nodes:[{title,label,type,context,description,aliases,reusable_knowledge,reusable_event}],"
            "mentions:[{surface_text,label,role}],assertions:[{subject_ref,predicate,object_ref,"
            "object_literal,polarity,epistemic_status,viewpoint,context,confidence,"
            "importance_event}]}\n"
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
            raw_label = _model_text(item.get("label"))
            raw_title = _model_text(item.get("title"))
            label = raw_title or raw_label
            if not label:
                raise ValueError("model node requires title or label")
            if label not in content:
                raise ValueError("model node label is not grounded in Episode")
            proposed_type = _model_text(item.get("type")) or "concept"
            type_spec = resolve_memory_node_type(proposed_type)
            node_type = proposed_type
            node_properties: dict[str, Any] = {}
            description_kind = "description"
            if type_spec.domain == "knowledge":
                node_type = "knowledge"
                if item.get("reusable_knowledge") is not True:
                    raise ValueError(
                        "knowledge node proposals require reusable_knowledge=true"
                    )
                node_properties["knowledge_kind"] = str(
                    item.get("knowledge_kind") or memory_knowledge_kind(proposed_type)
                )
                label = _validate_knowledge_title(label, content)
                description_kind = "context"
            elif type_spec.domain == "entity":
                node_type = type_spec.kind
            elif type_spec.domain == "event":
                node_type = "event"
            elif type_spec.domain == "technical":
                raise ValueError("technical node types are not valid model proposals")
            # Reusable semantic anchors share identity across Episodes. An
            # event is admitted only when the proposal explicitly marks it as
            # reusable; an ordinary Episode remains the source unit.
            if type_spec.domain == "event" and item.get("reusable_event") is not True:
                raise ValueError("event node proposals require reusable_event=true")
            node_id = _projection_id("node:", node_type, "elfie", label)
            labels_to_ids[label] = node_id
            # Keep the source explanation on the Node as context/description;
            # the canonical label remains the short title above.  When a
            # knowledge proposal omits context, the complete Episode is the
            # auditable fallback rather than another model-invented summary.
            raw_description = _model_text(
                item.get("context")
                if type_spec.domain == "knowledge"
                else item.get("description")
            )
            if raw_description is None and type_spec.domain == "knowledge":
                raw_description = _model_text(item.get("description"))
            if raw_description is None and type_spec.domain == "knowledge":
                raw_description = content
            grounded_description = (
                raw_description
                if raw_description and raw_description in content
                else None
            )
            if type_spec.domain == "knowledge" and grounded_description is None:
                raise ValueError("knowledge context must be grounded in Episode")
            if raw_label and raw_label != label and raw_label in content:
                # Preserve references emitted in the legacy label field while
                # using the validated title as the canonical graph label.
                labels_to_ids[raw_label] = node_id
            if "importance" in item:
                raise ValueError(
                    "model importance must be expressed as importance_event"
                )
            importance_event = _model_importance_event(item.get("importance_event"))
            nodes.append(
                NodeInput(
                    node_id=node_id,
                    node_type=node_type,
                    canonical_label=label,
                    description=grounded_description,
                    properties=node_properties,
                    confidence=_model_score(item.get("confidence"), 0.6),
                    # Importance is an admission baseline plus an auditable
                    # event.  Do not materialize a second, lossy score here;
                    # the adapter folds the event atomically with the source.
                    importance=episode.importance,
                    initial_importance=episode.initial_importance,
                    importance_event_class=importance_event,
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
                            kind=description_kind,
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
            start = _model_int(item.get("span_start"))
            if start is None:
                start = content.find(surface)
            mentions.append(
                MentionInput(
                    episode_id=episode.episode_id,
                    surface_text=surface,
                    node_id=resolved_node_id,
                    resolution_state=("resolved" if resolved_node_id else "unresolved"),
                    role=_model_text(item.get("role")),
                    span_start=start if start >= 0 else None,
                    span_end=(start + len(surface)) if start >= 0 else None,
                    confidence=_model_score(item.get("confidence"), 0.6),
                )
            )

        assertions: list[AssertionInput] = []
        symmetric_assertions: set[tuple[str, str, str, str, str, str, str | None]] = (
            set()
        )
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
            predicate = resolve_predicate(_required_model_text(item, "predicate"))
            if predicate in NON_SEMANTIC_LEGACY_PREDICATES:
                raise ValueError(
                    f"model predicate is legacy/non-semantic and cannot be written: {predicate}"
                )
            importance_event = _model_importance_event(item.get("importance_event"))
            if "importance" in item:
                raise ValueError(
                    "model importance must be expressed as importance_event"
                )
            subject_id = labels_to_ids[subject_ref]
            relation = relation_spec(predicate)
            if (
                relation is not None
                and relation.symmetric
                and object_node_id is not None
            ):
                subject_id, object_node_id = sorted((subject_id, object_node_id))
                symmetric_key = (
                    predicate,
                    subject_id,
                    object_node_id,
                    str(item.get("polarity") or "positive"),
                    str(item.get("epistemic_status") or "known"),
                    str(item.get("viewpoint") or ""),
                    _model_text(item.get("context")),
                )
                if symmetric_key in symmetric_assertions:
                    continue
                symmetric_assertions.add(symmetric_key)
            relation_baseline = relation_importance(
                predicate,
                None if relation is not None else episode.importance,
            )
            assertions.append(
                AssertionInput(
                    subject_id=subject_id,
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
                    importance=relation_baseline,
                    initial_importance=(
                        relation_baseline
                        if relation is not None
                        else episode.initial_importance
                    ),
                    importance_event_class=importance_event,
                    object_literal_type=_model_text(item.get("object_literal_type")),
                    evidence_ids=(evidence_id,),
                )
            )
        if (
            not assertions
            and len(nodes) == len(base_nodes)
            and len(mentions) == len(base_mentions)
        ):
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
            "长老": "person",
            "地球": "place",
            "精灵巢": "place",
            "花园": "place",
            "厨房": "place",
            "香菜": "object",
            "鱼味": "object",
            "鸡肉": "object",
            "猫": "elfie",
            "狗": "elfie",
        }
        found: list[tuple[str, str, int]] = []
        for label, kind in dictionary.items():
            start = content.find(label)
            if start >= 0:
                found.append((label, kind, start))
        # Knowledge is deliberately absent from this local fallback.  A
        # reusable knowledge Node needs a model-supplied title, context and
        # admission decision; ordinary text remains an Episode until then.
        return sorted(found, key=lambda item: (item[2], item[0]))


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


def _model_importance_event(value: object) -> str | None:
    """Accept only policy-owned importance levels from a model proposal.

    Omission is meaningful: a model that did not make a semantic appraisal
    must not silently turn an extraction into an importance update.  The
    source Episode's admission value remains the baseline in that case.
    """
    if value is None:
        return None
    event_class = str(value).strip()
    if event_class not in {"routine", "meaningful", "major", "core"}:
        raise ValueError("model importance_event is not an allowed policy level")
    return event_class


def _validate_knowledge_title(title: str, content: str) -> str:
    """Admit one short, source-grounded title for a knowledge Node.

    A full Episode remains the source text.  Treating that text as the
    canonical label makes the graph unreadable and creates a fake one-node
    summary, so reject it at the model boundary instead of repairing it with
    a heuristic title.
    """

    candidate = title.strip()
    source = content.strip()
    if not candidate:
        raise ValueError("knowledge title must not be blank")
    if len(candidate) > _KNOWLEDGE_TITLE_MAX_CHARS:
        raise ValueError("knowledge title is too long")
    if any(mark in candidate for mark in _KNOWLEDGE_TITLE_SENTENCE_MARKS):
        raise ValueError("knowledge title must be a short phrase, not a sentence")
    if candidate == source and len(candidate) >= 20:
        raise ValueError("knowledge title must not duplicate the complete Episode")
    # A punctuation-free provider response can still be a whole paragraph.
    # Reject labels that consume almost all of a long source instead of
    # silently inventing a lossy title.
    if len(candidate) >= 20 and len(candidate) >= len(source) * 0.75:
        raise ValueError("knowledge title is too close to the complete Episode")
    return candidate


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
    *,
    node_id: str,
    text: str,
    evidence_id: str,
    confidence: float,
    kind: str = "description",
) -> DescriptionInput:
    return DescriptionInput(
        node_id=node_id,
        text=text,
        kind=kind,
        evidence_id=evidence_id,
        confidence=confidence,
    )
