"""Commit one validated Genesis bundle into the Elfie's Memory owner.

Genesis is a one-time semantic compiler.  This module is the single hand-off
adapter from its typed bundle to the existing source-first Memory port.  It
does not load world configuration, Profile defaults, or model output; all
semantic choices have already been made by :mod:`elfie.genesis.compiler`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Literal

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    EvidenceInput,
    GenesisSubmissionReceipt,
    NodeInput,
    SourceReference,
)
from elfie.brain.memory.memory_store import (
    GenesisSubmissionConflict,
    MemoryStorePort,
)
from elfie.brain.memory.ontology import MemoryOntologySnapshot
from elfie.brain.memory.predicates import (
    relation_context,
    relation_importance,
)

from .contracts import (
    GenesisBundle,
    GenesisValidationError,
    validate_genesis_bundle,
)
from .serialization import (
    ENTITY_NODE_PREFIX,
    EPISODE_NODE_PREFIX,
    PERSON_NODE_PREFIX,
    PLACE_NODE_PREFIX,
    SELF_NODE_PREFIX,
    genesis_content_hash,
    knowledge_group_id,
    knowledge_groups,
    knowledge_member_text,
    knowledge_summary_text,
    output_ids_hash,
    planned_genesis_output_ids,
    safe_component,
)


@dataclass(frozen=True)
class GenesisCommitReceipt:
    """Minimal evidence that one Genesis submission was committed."""

    manifest_id: str
    status: Literal["committed", "duplicate"]
    node_ids: tuple[str, ...]
    idempotency_key_digest: str = ""
    content_hash: str = ""
    output_ids_hash: str = ""
    compiler_version: str = ""
    schema_version: int = 1
    committed_at: str = ""


class GenesisMemoryCommitter:
    """Materialize a typed bundle through one atomic Memory submission."""

    def __init__(self, ontology: MemoryOntologySnapshot | None = None) -> None:
        self._ontology = ontology

    def commit(
        self, bundle: GenesisBundle, storage: MemoryStorePort
    ) -> GenesisCommitReceipt:
        validate_genesis_bundle(bundle)
        expected_ids = planned_genesis_output_ids(bundle)
        if tuple(bundle.manifest.output_ids) != expected_ids:
            raise GenesisValidationError(
                "InitializationManifest.output_ids 与 Genesis 输出不一致"
            )
        computed_hash = genesis_content_hash(bundle)
        if bundle.manifest.content_hash != computed_hash:
            raise GenesisValidationError(
                "InitializationManifest.content_hash 与 Genesis 内容不一致"
            )

        profile = bundle.profile_draft.profile
        elfie_id = profile.identity.elfie_id
        key_digest = _idempotency_key_digest(bundle.manifest.idempotency_key)
        inventory_hash = output_ids_hash(expected_ids)
        submission = getattr(storage, "genesis_submission", None)
        get_submission = getattr(storage, "get_genesis_submission", None)
        if not callable(submission) or not callable(get_submission):
            raise TypeError("Genesis requires source-first Memory storage")
        ontology = self._ontology or getattr(storage, "ontology", None)
        if not isinstance(ontology, MemoryOntologySnapshot):
            raise TypeError("Genesis requires the injected Memory ontology snapshot")
        validate_genesis_bundle(bundle, ontology)

        existing_submission = get_submission(key_digest)
        if existing_submission is not None:
            self._verify_existing_submission(existing_submission, bundle, key_digest)

        now = datetime.now(timezone.utc).isoformat()
        try:
            with submission(
                submission_id=key_digest,
                manifest_id=bundle.manifest.manifest_id,
                source_version=bundle.manifest.compiler_version,
                content_sha256=bundle.manifest.content_hash,
                expected_ids=expected_ids,
                elfie_id=elfie_id,
            ) as accepted:
                result = (
                    self._commit_bundle(
                        bundle, storage, now, key_digest, inventory_hash, ontology
                    )
                    if accepted
                    else None
                )
        except GenesisSubmissionConflict as error:
            if error.kind == "manifest":
                raise GenesisValidationError(
                    "该 Elfie 已经用另一个 Genesis manifest 初始化，不能覆盖已有生命起点"
                ) from error
            if error.kind == "output_owner":
                raise GenesisValidationError(
                    "该 Elfie 的 Genesis 输出已归属另一个提交，不能用新幂等身份覆盖"
                ) from error
            if error.kind == "output_ids":
                raise GenesisValidationError(
                    "该 Elfie 的 Genesis 输出清单与已提交版本不一致"
                ) from error
            if error.kind == "identity":
                raise GenesisValidationError(
                    "该 Elfie 的 Genesis 幂等身份与已提交版本不一致"
                ) from error
            raise

        committed_submission = get_submission(key_digest)
        if committed_submission is None:
            raise GenesisValidationError(
                "Memory 已结束 Genesis 提交，但事务账本中没有完成回执"
            )
        self._verify_existing_submission(committed_submission, bundle, key_digest)
        if result is not None:
            return replace(result, committed_at=committed_submission.committed_at)
        return GenesisCommitReceipt(
            manifest_id=bundle.manifest.manifest_id,
            status="duplicate",
            node_ids=expected_ids,
            idempotency_key_digest=key_digest,
            content_hash=bundle.manifest.content_hash,
            output_ids_hash=inventory_hash,
            compiler_version=bundle.manifest.compiler_version,
            schema_version=bundle.manifest.schema_version,
            committed_at=committed_submission.committed_at,
        )

    @staticmethod
    def _verify_existing_submission(
        receipt: GenesisSubmissionReceipt,
        bundle: GenesisBundle,
        submission_id: str,
    ) -> None:
        if receipt.submission_id != submission_id:
            raise GenesisValidationError("Genesis 提交回执的幂等身份不一致")
        if receipt.elfie_id != bundle.profile_draft.profile.identity.elfie_id:
            raise GenesisValidationError("Genesis 提交回执属于另一只精灵")
        if receipt.manifest_id != bundle.manifest.manifest_id:
            raise GenesisValidationError(
                "该 Elfie 已经用另一个 Genesis manifest 初始化，不能覆盖已有生命起点"
            )
        if receipt.content_sha256 != bundle.manifest.content_hash:
            raise GenesisValidationError(
                "该 Elfie 的 Genesis manifest 内容与已提交版本不一致"
            )
        if receipt.source_version != bundle.manifest.compiler_version:
            raise GenesisValidationError(
                "该 Elfie 的 Genesis 编译器版本与已提交版本不一致"
            )

    def _commit_bundle(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        now: str,
        key_digest: str,
        inventory_hash: str,
        ontology: MemoryOntologySnapshot,
    ) -> GenesisCommitReceipt:
        profile = bundle.profile_draft.profile
        elfie_id = profile.identity.elfie_id
        safe_elfie = safe_component(elfie_id)
        scope = f"elfie:{safe_elfie}"
        manifest = bundle.manifest
        manifest_id = manifest.manifest_id
        node_ids: list[str] = []

        self_id = f"{SELF_NODE_PREFIX}{safe_elfie}"
        selfhood = bundle.selfhood_state
        if selfhood is None or not selfhood.complete:
            raise GenesisValidationError("Genesis SelfhoodState 不完整")
        identity_core = selfhood.identity_core
        parent_seed = next(
            (
                relationship
                for relationship in bundle.relationship_seeds
                if relationship.role == "parent"
                and any(
                    person_id == "self"
                    for person_id, _ in relationship.child_birth_orders
                )
            ),
            None,
        )
        self_birth_order = (
            next(
                order
                for person_id, order in parent_seed.child_birth_orders
                if person_id == "self"
            )
            if parent_seed is not None
            else None
        )
        family_child_count = (
            len(parent_seed.child_birth_orders) if parent_seed is not None else None
        )
        self_description = selfhood.self_description
        if self_birth_order is not None and family_child_count is not None:
            self_description = (
                f"{self_description} 家庭排行第{self_birth_order}，"
                f"父母共有{family_child_count}名子女。"
            )

        self._upsert_node(
            storage,
            NodeInput(
                node_id=self_id,
                node_type="elfie",
                canonical_label=profile.identity.display_name,
                description=self_description,
                scope=scope,
                status="active",
                confidence=1.0,
                importance=1.0,
                retention_profile="stable",
                properties={
                    "entity_type": "elfie",
                    "elfie_id": elfie_id,
                    "display_name": profile.identity.display_name,
                    "species_id": identity_core.species_id
                    or profile.identity.species_id,
                    "species_name": identity_core.species_name or "",
                    "is_self": True,
                    "relationship_label": "self",
                    "family_birth_order": self_birth_order,
                    "family_child_count": family_child_count,
                },
            ),
        )
        node_ids.append(self_id)

        place_node_ids = self._write_places(bundle, storage, scope, now)
        node_ids.extend(place_node_ids.values())
        self._write_place_hierarchy(bundle, storage, place_node_ids, now, ontology)
        self._write_place_relations(bundle, storage, place_node_ids, now, ontology)

        person_node_ids: dict[str, str] = {}
        for relationship in bundle.relationship_seeds:
            target_key = relationship.object_id or relationship.person_id
            person_id = f"{PERSON_NODE_PREFIX}{safe_elfie}:{safe_component(target_key)}"
            target_node_type = relationship.object_kind
            ontology.validate_node_type(target_node_type)
            person_node_ids[target_key] = person_id
            person_node_ids[relationship.person_id] = person_id
            description = "；".join(
                item
                for item in (
                    f"关系角色：{relationship.role}",
                    f"物种：{relationship.person_species_id}"
                    if relationship.person_species_id
                    else "",
                    f"年龄：{relationship.age_years_at_genesis}岁"
                    if relationship.age_years_at_genesis is not None
                    and relationship.life_status == "alive"
                    else "",
                    f"关系形成于：{relationship.relationship_start_age}岁"
                    if relationship.relationship_start_age is not None
                    else "",
                    f"出生排行：第{relationship.birth_order}位"
                    if relationship.birth_order is not None
                    else "",
                    "子女排行："
                    + "、".join(
                        f"{person_id}第{order}位"
                        for person_id, order in relationship.child_birth_orders
                    )
                    if relationship.child_birth_orders
                    else "",
                    f"享年：{relationship.death_age_years_at_genesis}岁"
                    if relationship.death_age_years_at_genesis is not None
                    else "",
                    f"出生时我{relationship.birth_event_age_years}岁"
                    if relationship.birth_event_age_years is not None
                    else "",
                    f"离世时我{relationship.death_event_age_years}岁"
                    if relationship.death_event_age_years is not None
                    else "",
                    f"照护者：{', '.join(relationship.caregiver_person_ids)}"
                    if relationship.caregiver_person_ids
                    else "",
                    f"照护对象：{', '.join(relationship.care_recipient_person_ids)}"
                    if relationship.care_recipient_person_ids
                    else "",
                    f"职业线索：{relationship.vocation_id}"
                    if relationship.vocation_id
                    else "",
                    f"能力线索：{', '.join(relationship.competency_ids)}"
                    if relationship.competency_ids
                    else "",
                    *relationship.shared_facts,
                    *(f"未知：{item}" for item in relationship.unknown_facts),
                )
                if item
            )
            self._upsert_node(
                storage,
                NodeInput(
                    node_id=person_id,
                    node_type=target_node_type,
                    canonical_label=relationship.display_name,
                    description=description or None,
                    scope=scope,
                    status="active",
                    confidence=max(relationship.initial_trust, 0.5),
                    importance=relationship.importance,
                    properties={
                        "entity_type": target_node_type,
                        "object_kind": relationship.object_kind,
                        "person_id": relationship.person_id,
                        "relationship_id": relationship.stable_relationship_id,
                        "relationship_label": relationship.role,
                        "species_id": (
                            relationship.person_species_id
                            if relationship.object_kind == "elfie"
                            else ""
                        ),
                        "person_species_id": relationship.person_species_id,
                        "age_years_at_genesis": relationship.age_years_at_genesis,
                        "relationship_start_age": relationship.relationship_start_age,
                        "birth_order": relationship.birth_order,
                        "child_birth_orders": [
                            {"person_id": person_id, "birth_order": order}
                            for person_id, order in relationship.child_birth_orders
                        ],
                        "person_gender": relationship.person_gender,
                        "life_status": relationship.life_status,
                        "death_age_years_at_genesis": relationship.death_age_years_at_genesis,
                        "birth_event_age_years": relationship.birth_event_age_years,
                        "death_event_age_years": relationship.death_event_age_years,
                        "related_person_ids": list(relationship.related_person_ids),
                        "caregiver_person_ids": list(relationship.caregiver_person_ids),
                        "care_recipient_person_ids": list(
                            relationship.care_recipient_person_ids
                        ),
                        "vocation_id": relationship.vocation_id,
                        "competency_ids": list(relationship.competency_ids),
                        "eligible_episode_theme_ids": list(
                            relationship.eligible_episode_theme_ids
                        ),
                        "direction": relationship.direction,
                        "familiarity": relationship.familiarity,
                        "trust_score": relationship.initial_trust,
                        "is_owner": relationship.role in {"owner", "earth_household"},
                        "shared_facts": list(relationship.shared_facts),
                        "unknown_facts": list(relationship.unknown_facts),
                        "aliases": list(
                            dict.fromkeys(
                                (*relationship.aliases, *relationship.retrieval_terms)
                            )
                        ),
                        "episode_ids": list(relationship.episode_ids),
                    },
                ),
            )
            if person_id not in node_ids:
                node_ids.append(person_id)

        # Each topic chunk is a complete source Episode. Member spans preserve
        # the exact reviewed fact and its independent acquisition/provenance.
        groups = knowledge_groups(bundle)
        knowledge_sources: dict[str, tuple[str, int, int]] = {}
        for group_index, members in enumerate(groups):
            episode_id = knowledge_group_id(safe_elfie, members)
            sections: list[str] = []
            member_metadata: list[dict] = []
            cursor = 0
            for seed in members:
                section = knowledge_member_text(seed)
                start = cursor
                end = start + len(seed.content)
                properties = asdict(seed)
                properties.pop("graph_nodes")
                properties.pop("graph_assertions")
                properties.update(span_start=start, span_end=end)
                member_metadata.append(properties)
                knowledge_sources[seed.seed_id] = (episode_id, start, end)
                sections.append(section)
                cursor += len(section) + 2
            first = members[0]
            acquired_age = first.acquired_age_years
            storage.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"{manifest_id}:knowledge:{group_index}",
                    occurred_from=None,
                    occurrence_precision="unknown",
                    content_text="\n\n".join(sections),
                    summary_text=first.summary_text
                    or knowledge_summary_text(first.content),
                    event_kind="learning",
                    source_refs=tuple(
                        SourceReference(
                            source_id=seed.source_ref,
                            source_kind=seed.source,
                            locator=seed.seed_id,
                            source_version=seed.source_version,
                        )
                        for seed in members
                    ),
                    source_version=bundle.manifest.compiler_version,
                    importance=max(seed.importance for seed in members),
                    initial_importance=max(seed.importance for seed in members),
                    retention_profile="genesis",
                    attribution="told",
                    life_stage=first.acquired_stage or None,
                    temporal_label=f"{acquired_age}岁时获得的知识"
                    if acquired_age is not None
                    else "获得时间未知",
                    metadata={
                        "knowledge_id": f"topic:{first.topic}:{first.seed_id}",
                        "topic": first.topic,
                        "topic_bucket": first.topic,
                        "topic_member_ids": [seed.seed_id for seed in members],
                        "topic_member_index": group_index,
                        "topic_member_count": len(members),
                        "knowledge_members": member_metadata,
                        "aliases": list(
                            dict.fromkeys(
                                alias for seed in members for alias in seed.aliases
                            )
                        ),
                        "retrieval_terms": list(
                            dict.fromkeys(
                                term
                                for seed in members
                                for term in seed.retrieval_terms
                            )
                        ),
                        "recall_eligible": first.recall_eligible,
                        "acquired_age_years": acquired_age,
                        "genesis_time": {
                            "calendar": "elfaria_age",
                            "age_from": acquired_age,
                            "age_to": acquired_age + 1
                            if acquired_age is not None
                            else None,
                        },
                    },
                )
            )
            node_ids.append(episode_id)

        graph_ids = {
            node.node_id: f"{ENTITY_NODE_PREFIX}{safe_elfie}:{safe_component(node.node_id)}"
            for seed in bundle.knowledge_seeds
            for node in seed.graph_nodes
        }
        for seed in bundle.knowledge_seeds:
            for node in seed.graph_nodes:
                node_id = graph_ids[node.node_id]
                if node_id not in node_ids:
                    self._upsert_node(
                        storage,
                        replace(
                            node,
                            node_id=node_id,
                            scope=scope,
                            confidence=seed.initial_confidence,
                            importance=seed.importance,
                            retention_profile="genesis",
                            properties={
                                **node.properties,
                                "source_episode_ids": [
                                    knowledge_sources[member.seed_id][0]
                                    for member in bundle.knowledge_seeds
                                    if any(
                                        item.node_id == node.node_id
                                        for item in member.graph_nodes
                                    )
                                ],
                            },
                        ),
                    )
                    node_ids.append(node_id)
        for seed in bundle.knowledge_seeds:
            episode_id, start, end = knowledge_sources[seed.seed_id]
            for index, edge in enumerate(seed.graph_assertions):
                self._record_assertion(
                    storage,
                    replace(
                        edge,
                        subject_id=graph_ids[edge.subject_id],
                        object_node_id=graph_ids[edge.object_node_id]
                        if edge.object_node_id
                        else None,
                        confidence=seed.initial_confidence,
                    ),
                    EvidenceInput(
                        evidence_id=f"genesis:evidence:entity:{safe_elfie}:{safe_component(seed.seed_id)}:{index}",
                        source_type="episode",
                        source_id=episode_id,
                        excerpt=seed.content,
                        span_start=start,
                        span_end=end,
                        source_version=bundle.manifest.compiler_version,
                        attribution="told",
                    ),
                )

        episode_source_ids: dict[str, str] = {}
        episode_source_versions: dict[str, str] = {}
        for sequence_index, seed in enumerate(bundle.episode_seeds):
            episode_id = (
                f"{EPISODE_NODE_PREFIX}{safe_elfie}:{safe_component(seed.seed_id)}"
            )
            episode_source_ids[seed.seed_id] = episode_id
            episode_source_versions[seed.seed_id] = seed.source_version
            if seed.occurred_from is None and seed.occurred_to is not None:
                raise GenesisValidationError(
                    "EpisodeSeed.occurred_to 不能在缺少 occurred_from 时单独提供"
                )
            precision: Literal["exact", "range", "unknown"] = (
                "unknown"
                if seed.occurred_from is None
                else "range"
                if seed.occurred_to is not None
                else "exact"
            )
            source_ref = SourceReference(
                source_id=seed.source_ref,
                source_kind=seed.source,
                locator=seed.seed_id,
                source_version=seed.source_version,
            )
            storage.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"{manifest_id}:episode:{seed.seed_id}",
                    occurred_from=seed.occurred_from,
                    occurred_to=seed.occurred_to,
                    occurrence_precision=precision,
                    content_text=seed.content,
                    summary_text=seed.result or seed.impact or None,
                    event_kind=seed.event_kind,
                    source_refs=(source_ref,),
                    source_event_ids=(),
                    source_version=seed.source_version,
                    importance=seed.importance,
                    initial_importance=seed.importance,
                    retention_profile="genesis",
                    emotion=seed.emotional_tone,
                    emotion_intensity=seed.emotion_intensity,
                    life_stage=seed.life_stage,
                    temporal_label=seed.temporal_label,
                    attribution="observed",
                    metadata={
                        "seed_id": seed.seed_id,
                        "result": seed.result,
                        "feeling": seed.feeling,
                        "impact": seed.impact,
                        "place_ids": list(seed.place_ids),
                        "observed_place_ids": list(seed.observed_place_ids),
                        "route_ids": list(seed.route_ids),
                        "person_ids": list(seed.person_ids),
                        "visit_count": seed.visit_count,
                        "travel_days": seed.travel_days,
                        "stay_days": seed.stay_days,
                        "visit_age_years": list(seed.visit_age_years),
                        "purposes": list(seed.purposes),
                        "predecessor_ids": list(seed.predecessor_ids),
                        "related_ids": list(seed.related_ids),
                        "causal_links": list(seed.causal_links),
                        "theme_id": seed.theme_id,
                        "age_years_at_event": seed.age_years_at_event,
                        "sequence_index": sequence_index,
                        "genesis_time": {
                            "calendar": "elfaria_age",
                            "age_from": seed.age_years_at_event,
                            "age_to": seed.age_years_at_event + 1
                            if seed.age_years_at_event is not None
                            else None,
                            "relative_to": "arrival-nest",
                            "relation": "at"
                            if seed.seed_id == "arrival-nest"
                            else "before",
                            "precision": "age_year"
                            if seed.age_years_at_event is not None
                            else "relative",
                            "travel_local_days": seed.travel_days or None,
                            "stay_local_days": seed.stay_days
                            if seed.theme_id == "predeparture-training"
                            or seed.seed_id.startswith("visit:")
                            else None,
                            "life_stage": seed.life_stage,
                            "sequence_index": sequence_index,
                            "predecessor_ids": list(seed.predecessor_ids),
                        },
                    },
                )
            )
            node_ids.append(episode_id)

            # Keep actual episode locations queryable in the initial graph as
            # well as in the Episode payload.  The Episode remains the source
            # of truth for wording, route metadata and chronology; this typed
            # edge is only the evidenced personal contact projection.
            for place_id in seed.place_ids:
                place_node = place_node_ids.get(place_id)
                if place_node is None:
                    raise GenesisValidationError(
                        f"EpisodeSeed 引用的地点没有生成节点: {place_id}"
                    )
                place_seed = next(
                    place for place in bundle.place_seeds if place.place_id == place_id
                )
                self._record_assertion(
                    storage,
                    AssertionInput(
                        self_id,
                        "visits",
                        object_node_id=place_node,
                        context=relation_context(
                            ontology,
                            "genesis_episode_place",
                            predicate="visits",
                            role="visited",
                        ),
                        epistemic_status="known",
                        confidence=1.0,
                        importance=relation_importance(
                            ontology, "visits", place_seed.importance
                        ),
                    ),
                    EvidenceInput(
                        evidence_id=(
                            f"genesis:evidence:episode-place:{safe_elfie}:"
                            f"{safe_component(seed.seed_id)}:{safe_component(place_id)}"
                        ),
                        source_type="episode",
                        source_id=episode_id,
                        excerpt=seed.content,
                        source_version=seed.source_version,
                        captured_at=now,
                    ),
                )
            for place_id in seed.observed_place_ids:
                place_node = place_node_ids.get(place_id)
                if place_node is None:
                    raise GenesisValidationError(
                        f"EpisodeSeed 引用的观察地点没有生成节点: {place_id}"
                    )
                place_seed = next(
                    place for place in bundle.place_seeds if place.place_id == place_id
                )
                self._record_assertion(
                    storage,
                    AssertionInput(
                        self_id,
                        "witnessed",
                        object_node_id=place_node,
                        context=relation_context(
                            ontology,
                            "genesis_episode_place",
                            predicate="witnessed",
                            role="observed",
                        ),
                        epistemic_status="known",
                        confidence=1.0,
                        importance=relation_importance(
                            ontology, "witnessed", place_seed.importance
                        ),
                    ),
                    EvidenceInput(
                        evidence_id=(
                            f"genesis:evidence:episode-observed-place:{safe_elfie}:"
                            f"{safe_component(seed.seed_id)}:{safe_component(place_id)}"
                        ),
                        source_type="episode",
                        source_id=episode_id,
                        excerpt=seed.content,
                        source_version=seed.source_version,
                        captured_at=now,
                    ),
                )

        for relationship in bundle.relationship_seeds:
            target_key = relationship.object_id or relationship.person_id
            target_node = person_node_ids.get(target_key) or place_node_ids.get(
                target_key
            )
            if target_node is None:
                raise GenesisValidationError(
                    f"RelationshipSeed 引用的对象没有生成节点: {target_key}"
                )
            related_episode = next(
                (
                    episode_source_ids[episode_id]
                    for episode_id in relationship.episode_ids
                    if episode_id in episode_source_ids
                ),
                None,
            )
            related_episode_version = next(
                (
                    episode_source_versions[episode_key]
                    for episode_key in relationship.episode_ids
                    if episode_key in episode_source_versions
                ),
                relationship.source_version,
            )
            relation_evidence_id = (
                f"genesis:evidence:relationship:{safe_elfie}:"
                f"{safe_component(relationship.stable_relationship_id)}"
            )
            relation_predicate = _relationship_predicate(relationship.role)
            ontology.predicate_spec(relation_predicate)
            self._record_assertion(
                storage,
                AssertionInput(
                    self_id,
                    relation_predicate,
                    object_node_id=target_node,
                    context=relation_context(
                        ontology,
                        "genesis_relationship",
                        predicate=relation_predicate,
                        specificity=(
                            "unspecified" if relation_predicate == "kin_of" else None
                        ),
                        role=relationship.role,
                    ),
                    epistemic_status=(
                        "known" if relationship.certainty == "high" else "believed"
                    ),
                    confidence=max(relationship.initial_trust, 0.5),
                    importance=relation_importance(
                        ontology, relation_predicate, relationship.importance
                    ),
                ),
                EvidenceInput(
                    evidence_id=relation_evidence_id,
                    source_type="episode" if related_episode else "seed",
                    source_id=related_episode or relationship.source_ref,
                    excerpt=(
                        f"{relationship.display_name}: {relationship.role}; "
                        f"{'; '.join(relationship.shared_facts)}"
                    ),
                    source_version=related_episode_version,
                    captured_at=now,
                ),
            )

        arrival_episode = episode_source_ids.get("arrival-nest")
        owner_home = next(
            (place for place in bundle.place_seeds if place.kind == "owner_home"), None
        )
        nest = next(
            (place for place in bundle.place_seeds if place.kind == "earth_home"), None
        )
        if arrival_episode and owner_home and nest:
            residents = [(self_id, nest.place_id)]
            residents.extend(
                (person_node_ids[relationship.person_id], owner_home.place_id)
                for relationship in bundle.relationship_seeds
                if relationship.role == "owner" and relationship.object_kind == "person"
            )
            for resident_id, place_id in residents:
                self._record_assertion(
                    storage,
                    AssertionInput(
                        resident_id, "lives_in", object_node_id=place_node_ids[place_id]
                    ),
                    EvidenceInput(
                        evidence_id=f"genesis:evidence:residence:{resident_id}",
                        source_type="episode",
                        source_id=arrival_episode,
                        excerpt=storage.get_episode(arrival_episode).content_text,
                        source_version=episode_source_versions["arrival-nest"],
                        captured_at=now,
                    ),
                )

        output_node_ids = tuple(node_ids)
        self._write_person_links(
            bundle,
            storage,
            person_node_ids,
            self_id,
            now,
            ontology,
        )
        if output_node_ids != tuple(manifest.output_ids):
            raise GenesisValidationError("Genesis 实际输出 ID 与 Manifest 声明不一致")
        return GenesisCommitReceipt(
            manifest_id=manifest_id,
            status="committed",
            node_ids=output_node_ids,
            idempotency_key_digest=key_digest,
            content_hash=manifest.content_hash,
            output_ids_hash=inventory_hash,
            compiler_version=manifest.compiler_version,
            schema_version=manifest.schema_version,
            committed_at=now,
        )

    def _write_person_links(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        person_node_ids: dict[str, str],
        self_id: str,
        now: str,
        ontology: MemoryOntologySnapshot,
    ) -> None:
        """Persist the bounded family graph edges without creating new people."""

        safe_elfie = safe_component(bundle.profile_draft.profile.identity.elfie_id)
        resolved = {"self": self_id, **person_node_ids}
        seen: set[tuple[str, str]] = set()
        for relationship in bundle.relationship_seeds:
            source = resolved.get(relationship.person_id)
            if source is None:
                continue
            for target_key in relationship.related_person_ids:
                target = resolved.get(target_key)
                if target is None or target == source:
                    continue
                pair = tuple(sorted((source, target)))
                if pair in seen:
                    continue
                seen.add(pair)
                evidence_id = (
                    f"genesis:evidence:person-link:{safe_elfie}:"
                    f"{safe_component(relationship.person_id)}:{safe_component(target_key)}"
                )
                self._record_assertion(
                    storage,
                    AssertionInput(
                        pair[0],
                        "kin_of",
                        object_node_id=pair[1],
                        context=relation_context(
                            ontology,
                            "genesis_family_graph",
                            predicate="kin_of",
                        ),
                        epistemic_status="known",
                        confidence=max(relationship.initial_trust, 0.5),
                        importance=relation_importance(
                            ontology, "kin_of", relationship.importance
                        ),
                    ),
                    EvidenceInput(
                        evidence_id=evidence_id,
                        source_type="seed",
                        source_id=relationship.source_ref,
                        excerpt=(
                            f"{relationship.display_name} 与 {target_key} "
                            "属于同一已验证家庭或核心关系图。"
                        ),
                        source_version=relationship.source_version,
                        captured_at=now,
                    ),
                )

    @staticmethod
    def _upsert_node(storage: MemoryStorePort, node: NodeInput) -> None:
        upsert = getattr(storage, "upsert_node_record", None)
        if not callable(upsert):
            raise TypeError("source-first Memory storage lacks node upsert")
        upsert(node)

    @staticmethod
    def _record_assertion(
        storage: MemoryStorePort,
        assertion: AssertionInput,
        evidence: EvidenceInput,
    ) -> None:
        record = getattr(storage, "record_sourced_assertion", None)
        if not callable(record):
            raise TypeError("source-first Memory storage lacks sourced assertions")
        record(assertion, evidence)

    def _write_places(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        scope: str,
        now: str,
    ) -> dict[str, str]:
        safe_elfie = safe_component(bundle.profile_draft.profile.identity.elfie_id)
        place_node_ids: dict[str, str] = {}
        for place in bundle.place_seeds:
            node_id = (
                f"{PLACE_NODE_PREFIX}{safe_elfie}:{safe_component(place.place_id)}"
            )
            place_node_ids[place.place_id] = node_id
            self._upsert_node(
                storage,
                NodeInput(
                    node_id=node_id,
                    node_type=place.node_type,
                    canonical_label=place.label,
                    description=place.description or None,
                    scope=scope,
                    status="active",
                    confidence=1.0,
                    importance=place.importance,
                    properties={
                        "entity_level": "instance",
                        "entity_type": place.node_type,
                        "place_id": place.place_id,
                        "kind": place.kind,
                        "parent_id": place.parent_id,
                        "visibility": place.visibility,
                        "source_ref": place.source_ref,
                        "aliases": list(place.aliases),
                        "metadata": dict(place.metadata),
                    },
                ),
            )
        return place_node_ids

    def _write_place_hierarchy(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        place_node_ids: dict[str, str],
        now: str,
        ontology: MemoryOntologySnapshot,
    ) -> None:
        """Persist the explicit place seed hierarchy as typed graph facts.

        ``PlaceSeed.parent_id`` is already an approved Genesis fact.  Keeping
        it only in node properties makes the hierarchy invisible to graph
        traversal and reverse lookup, so materialize the bounded child →
        parent relation when both endpoints are part of this submission.
        Planet roots, including Earth, are explicit typed seeds; every
        nonempty parent has been validated within the same submission.
        """

        safe_elfie = safe_component(bundle.profile_draft.profile.identity.elfie_id)
        for place in bundle.place_seeds:
            parent_node = place_node_ids.get(place.parent_id)
            child_node = place_node_ids.get(place.place_id)
            if child_node is None or parent_node is None:
                continue
            evidence_id = (
                f"genesis:evidence:place-hierarchy:{safe_elfie}:"
                f"{safe_component(place.place_id)}"
            )
            self._record_assertion(
                storage,
                AssertionInput(
                    child_node,
                    "located_in",
                    object_node_id=parent_node,
                    context=relation_context(
                        ontology,
                        "genesis_place_hierarchy",
                        predicate="located_in",
                    ),
                    epistemic_status="known",
                    confidence=1.0,
                    importance=relation_importance(ontology, "located_in"),
                ),
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="seed",
                    source_id=place.source_ref or f"place:{place.place_id}",
                    excerpt=f"{place.label} 位于 {next((item.label for item in bundle.place_seeds if item.place_id == place.parent_id), place.parent_id)}。",
                    source_version=bundle.manifest.compiler_version,
                    captured_at=now,
                ),
            )

    def _write_place_relations(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        place_node_ids: dict[str, str],
        now: str,
        ontology: MemoryOntologySnapshot,
    ) -> None:
        """Persist the reviewed non-hierarchical public geography relations."""

        safe_elfie = safe_component(bundle.profile_draft.profile.identity.elfie_id)
        for relation in bundle.place_relation_seeds:
            subject_node = place_node_ids[relation.subject_id]
            object_node = place_node_ids[relation.object_id]
            try:
                ontology.predicate_spec(relation.relation)
            except ValueError as error:
                raise GenesisValidationError(
                    f"地点关系没有注册语义: {relation.relation}"
                ) from error
            evidence_id = (
                f"genesis:evidence:place-relation:{safe_elfie}:"
                f"{safe_component(relation.subject_id)}:"
                f"{safe_component(relation.relation)}:{safe_component(relation.object_id)}"
            )
            self._record_assertion(
                storage,
                AssertionInput(
                    subject_node,
                    relation.relation,
                    object_node_id=object_node,
                    context=json.dumps(
                        dict(relation.qualifiers), ensure_ascii=False, sort_keys=True
                    )
                    if relation.qualifiers
                    else relation_context(
                        ontology,
                        "genesis_place_relation",
                        predicate=relation.relation,
                        role=relation.relation,
                    ),
                    epistemic_status="known",
                    confidence=1.0,
                    importance=relation_importance(
                        ontology, relation.relation, relation.importance
                    ),
                ),
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="seed",
                    source_id=relation.source_ref,
                    excerpt=(
                        f"{relation.subject_id} {relation.relation} "
                        f"{relation.object_id}。"
                    ),
                    source_version=bundle.manifest.compiler_version,
                    captured_at=now,
                ),
            )


def _relationship_predicate(role: str) -> str:
    """Map a Genesis relationship role to one registered semantic predicate."""

    role_map = {
        "family": "kin_of",
        "parent": "child_of",
        "child": "parent_of",
        "sibling": "sibling_of",
        "grandparent": "kin_of",
        "aunt_uncle": "kin_of",
        "partner": "kin_of",
        "friend": "friend_of",
        "teacher": "student_of",
        "learning_keeper": "student_of",
        "neighbor": "neighbor_of",
        "owner": "owned_by",
        "earth_household": "member_of",
        "mentor": "mentored_by",
        "route_keeper": "guided_by",
        "departure_guide": "guided_by",
        "program_contact": "acquaintance_of",
        "earth_contact": "acquaintance_of",
        "elder": "acquaintance_of",
    }
    try:
        return role_map[role]
    except KeyError as exc:
        raise GenesisValidationError(
            f"Genesis relationship role 未注册，拒绝生成通用关系: {role}"
        ) from exc


def _idempotency_key_digest(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise GenesisValidationError("Genesis 幂等键不能为空")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ("GenesisCommitReceipt", "GenesisMemoryCommitter")
