"""Commit one validated Genesis bundle into the Elfie's Memory owner.

Genesis is a one-time semantic compiler.  This module is the single hand-off
adapter from its typed bundle to the existing source-first Memory port.  It
does not load world configuration, Profile defaults, or model output; all
semantic choices have already been made by :mod:`elfie.genesis.compiler`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    DescriptionInput,
    EvidenceInput,
    MentionInput,
    NodeInput,
    SourceReference,
)
from elfie.brain.memory.memory_store import MemoryStorePort

from .contracts import GenesisBundle, GenesisValidationError, validate_genesis_bundle
from .serialization import (
    EPISODE_NODE_PREFIX,
    EVENT_NODE_PREFIX,
    GENESIS_RECEIPT_PREFIX,
    KNOWLEDGE_NODE_PREFIX,
    PERSON_NODE_PREFIX,
    PLACE_NODE_PREFIX,
    SELF_MODEL_PREFIX,
    SELF_NODE_PREFIX,
    genesis_content_hash,
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
        marker_id = f"{GENESIS_RECEIPT_PREFIX}{elfie_id}"
        key_digest = _idempotency_key_digest(bundle.manifest.idempotency_key)
        inventory_hash = output_ids_hash(expected_ids)
        submission = getattr(storage, "genesis_submission", None)
        if not callable(submission):
            raise TypeError("Genesis requires source-first Memory storage")

        existing_marker = storage.get_graph_node(marker_id)
        if existing_marker is not None:
            self._verify_existing_marker(existing_marker, bundle)
            return GenesisCommitReceipt(
                manifest_id=bundle.manifest.manifest_id,
                status="duplicate",
                node_ids=_marker_node_ids(existing_marker),
                idempotency_key_digest=key_digest,
                content_hash=bundle.manifest.content_hash,
                output_ids_hash=inventory_hash,
                compiler_version=bundle.manifest.compiler_version,
                schema_version=bundle.manifest.schema_version,
                committed_at=str(existing_marker.properties.get("committed_at", "")),
            )

        now = datetime.now(timezone.utc).isoformat()
        with submission(
            submission_id=key_digest,
            manifest_id=bundle.manifest.manifest_id,
            source_version=bundle.manifest.compiler_version,
            content_sha256=bundle.manifest.content_hash,
            expected_ids=expected_ids,
            elfie_id=elfie_id,
        ) as accepted:
            if not accepted:
                marker = storage.get_graph_node(marker_id)
                if marker is None:
                    raise GenesisValidationError(
                        "Genesis submission was marked duplicate without a completion marker"
                    )
                return GenesisCommitReceipt(
                    manifest_id=bundle.manifest.manifest_id,
                    status="duplicate",
                    node_ids=_marker_node_ids(marker),
                    idempotency_key_digest=key_digest,
                    content_hash=bundle.manifest.content_hash,
                    output_ids_hash=inventory_hash,
                    compiler_version=bundle.manifest.compiler_version,
                    schema_version=bundle.manifest.schema_version,
                    committed_at=str(marker.properties.get("committed_at", "")),
                )
            return self._commit_bundle(bundle, storage, now, key_digest, inventory_hash)

    @staticmethod
    def _verify_existing_marker(marker, bundle: GenesisBundle) -> None:
        properties = marker.properties
        if properties.get("manifest_id") != bundle.manifest.manifest_id:
            raise GenesisValidationError(
                "该 Elfie 已经用另一个 Genesis manifest 初始化，不能覆盖已有生命起点"
            )
        if properties.get("content_hash") != bundle.manifest.content_hash:
            raise GenesisValidationError(
                "该 Elfie 的 Genesis manifest 内容与已提交版本不一致"
            )
        expected_digest = _idempotency_key_digest(bundle.manifest.idempotency_key)
        if properties.get("idempotency_key_digest") != expected_digest:
            raise GenesisValidationError(
                "该 Elfie 的 Genesis 幂等身份与已提交版本不一致"
            )
        if properties.get("output_ids_hash") != output_ids_hash(
            bundle.manifest.output_ids
        ):
            raise GenesisValidationError(
                "该 Elfie 的 Genesis 输出清单与已提交版本不一致"
            )

    def _commit_bundle(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        now: str,
        key_digest: str,
        inventory_hash: str,
    ) -> GenesisCommitReceipt:
        profile = bundle.profile_draft.profile
        elfie_id = profile.identity.elfie_id
        safe_elfie = safe_component(elfie_id)
        scope = f"elfie:{safe_elfie}"
        manifest = bundle.manifest
        manifest_id = manifest.manifest_id
        node_ids: list[str] = []

        self_id = f"{SELF_NODE_PREFIX}{safe_elfie}"
        self_model_id = f"{SELF_MODEL_PREFIX}{safe_elfie}"
        selfhood = bundle.selfhood_state
        if selfhood is None or not selfhood.complete:
            raise GenesisValidationError("Genesis SelfhoodState 不完整")
        identity_core = selfhood.identity_core

        self._upsert_node(
            storage,
            NodeInput(
                node_id=self_id,
                node_type="elfie",
                canonical_label=profile.identity.display_name,
                description=selfhood.self_description,
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
                },
            ),
        )
        node_ids.append(self_id)

        self._upsert_node(
            storage,
            NodeInput(
                node_id=self_model_id,
                node_type="self_model",
                canonical_label=bundle.self_model_seed.identity_summary,
                description=bundle.self_model_seed.identity_summary,
                scope=scope,
                status="active",
                confidence=1.0,
                importance=1.0,
                retention_profile="stable",
                properties={
                    "entity_type": "self_model",
                    "recall_eligible": False,
                    "known_facts": list(bundle.self_model_seed.known_facts),
                    "unknown_facts": list(bundle.self_model_seed.unknown_facts),
                    "knowledge_scope": list(bundle.self_model_seed.knowledge_scope),
                    "species_knowledge": list(bundle.self_model_seed.species_knowledge),
                    "skills": list(bundle.self_model_seed.skills),
                    "habits": list(bundle.self_model_seed.habits),
                    "preferences": list(bundle.self_model_seed.preferences),
                    "emotional_triggers": list(
                        bundle.self_model_seed.emotional_triggers
                    ),
                    "current_goal": bundle.self_model_seed.current_goal,
                    "earth_adaptation": list(bundle.self_model_seed.earth_adaptation),
                },
            ),
        )
        node_ids.append(self_model_id)
        self._record_assertion(
            storage,
            AssertionInput(
                self_id,
                "about",
                object_node_id=self_model_id,
                confidence=1.0,
                importance=1.0,
            ),
            EvidenceInput(
                evidence_id=f"genesis:evidence:self-model:{safe_elfie}",
                source_type="seed",
                source_id=self_model_id,
                excerpt=bundle.self_model_seed.identity_summary,
                source_version=manifest.compiler_version,
                captured_at=now,
            ),
        )

        place_node_ids, place_labels, place_projection = self._write_places(
            bundle, storage, scope, now
        )
        node_ids.extend(place_node_ids.values())

        person_node_ids: dict[str, str] = {}
        person_labels: dict[str, str] = {}
        person_projection: list[AliasInput | DescriptionInput | EvidenceInput] = []
        for relationship in bundle.relationship_seeds:
            target_key = relationship.object_id or relationship.person_id
            person_id = f"{PERSON_NODE_PREFIX}{safe_elfie}:{safe_component(target_key)}"
            person_node_ids[target_key] = person_id
            person_node_ids[relationship.person_id] = person_id
            person_labels[target_key] = relationship.display_name
            person_labels[relationship.person_id] = relationship.display_name
            description = "；".join(
                item
                for item in (
                    f"关系角色：{relationship.role}",
                    f"物种：{relationship.person_species_id}"
                    if relationship.person_species_id
                    else "",
                    f"年龄：{relationship.age_years_at_genesis}岁"
                    if relationship.age_years_at_genesis is not None
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
                    node_type="person",
                    canonical_label=relationship.display_name,
                    description=description or None,
                    scope=scope,
                    status="active",
                    confidence=max(relationship.initial_trust, 0.5),
                    importance=relationship.importance,
                    properties={
                        "entity_type": "person",
                        "person_id": relationship.person_id,
                        "relationship_id": relationship.stable_relationship_id,
                        "relationship_label": relationship.role,
                        "person_species_id": relationship.person_species_id,
                        "age_years_at_genesis": relationship.age_years_at_genesis,
                        "vocation_id": relationship.vocation_id,
                        "competency_ids": list(relationship.competency_ids),
                        "eligible_episode_theme_ids": list(
                            relationship.eligible_episode_theme_ids
                        ),
                        "direction": relationship.direction,
                        "familiarity": relationship.familiarity,
                        "trust_score": relationship.initial_trust,
                        "is_owner": relationship.role == "earth_household",
                        "shared_facts": list(relationship.shared_facts),
                        "unknown_facts": list(relationship.unknown_facts),
                        "episode_ids": list(relationship.episode_ids),
                    },
                ),
            )
            if person_id not in node_ids:
                node_ids.append(person_id)
            for alias_index, alias in enumerate(
                dict.fromkeys((*relationship.aliases, *relationship.retrieval_terms))
            ):
                evidence_id = (
                    f"genesis:evidence:person-alias:{safe_elfie}:"
                    f"{safe_component(relationship.stable_relationship_id)}:{alias_index}"
                )
                person_projection.extend(
                    (
                        AliasInput(
                            node_id=person_id,
                            alias=alias,
                            scope=scope,
                            evidence_id=evidence_id,
                            confidence=max(relationship.initial_trust, 0.5),
                        ),
                        EvidenceInput(
                            evidence_id=evidence_id,
                            source_type="seed",
                            source_id=relationship.source_ref,
                            excerpt=alias,
                            source_version=relationship.source_version,
                            captured_at=now,
                        ),
                    )
                )
            if description:
                evidence_id = (
                    f"genesis:evidence:person-description:{safe_elfie}:"
                    f"{safe_component(relationship.stable_relationship_id)}"
                )
                person_projection.extend(
                    (
                        DescriptionInput(
                            node_id=person_id,
                            text=description,
                            language="zh",
                            kind="genesis_relationship",
                            evidence_id=evidence_id,
                            confidence=max(relationship.initial_trust, 0.5),
                        ),
                        EvidenceInput(
                            evidence_id=evidence_id,
                            source_type="seed",
                            source_id=relationship.source_ref,
                            excerpt=description,
                            source_version=relationship.source_version,
                            captured_at=now,
                        ),
                    )
                )

        knowledge_projection: list[AliasInput | DescriptionInput | EvidenceInput] = []
        for knowledge in bundle.knowledge_seeds:
            knowledge_id = f"{KNOWLEDGE_NODE_PREFIX}{safe_elfie}:{safe_component(knowledge.seed_id)}"
            confidence = knowledge.initial_confidence
            recall_eligible = bool(knowledge.recall_eligible)
            epistemic_status: Literal["known", "believed", "uncertain", "reported"] = (
                "known"
                if knowledge.mastery == "known"
                else "uncertain"
                if knowledge.status == "unknown-boundary"
                or knowledge.mastery == "heard"
                else "believed"
            )
            predicate = (
                "knows_boundary" if knowledge.status == "unknown-boundary" else "knows"
            )
            evidence_base_id = (
                f"genesis:evidence:knowledge:{safe_elfie}:"
                f"{safe_component(knowledge.seed_id)}"
            )
            assertion_evidence_id = f"{evidence_base_id}:assertion"
            searchable = "\n".join(
                (
                    knowledge.content,
                    f"[{knowledge.topic}/{knowledge.level}/{knowledge.mastery}]",
                    *knowledge.aliases,
                    *knowledge.retrieval_terms,
                )
            )
            self._upsert_node(
                storage,
                NodeInput(
                    node_id=knowledge_id,
                    node_type="knowledge",
                    canonical_label=knowledge.content,
                    description=searchable,
                    scope=scope,
                    status="active" if recall_eligible else "unresolved",
                    confidence=confidence,
                    importance=knowledge.importance,
                    properties={
                        "entity_type": "knowledge",
                        "knowledge_id": knowledge.seed_id,
                        "source_kind": knowledge.source,
                        "source_ref": knowledge.source_ref,
                        "source_version": knowledge.source_version,
                        "certainty": knowledge.certainty,
                        "level": knowledge.level,
                        "mastery": knowledge.mastery,
                        "status": knowledge.status,
                        "scope": knowledge.scope,
                        "topic": knowledge.topic,
                        "eligibility": list(knowledge.eligibility),
                        "related_ids": list(knowledge.related_ids),
                        "prerequisite_ids": list(knowledge.prerequisite_ids),
                        "acquired_via": knowledge.acquired_via,
                        "acquired_stage": knowledge.acquired_stage,
                        "consultable_target_ids": list(
                            knowledge.consultable_target_ids
                        ),
                        "recall_eligible": recall_eligible,
                    },
                ),
            )
            node_ids.append(knowledge_id)
            for alias_index, alias in enumerate(
                dict.fromkeys((*knowledge.aliases, *knowledge.retrieval_terms))
            ):
                alias_evidence_id = f"{evidence_base_id}:alias:{alias_index}"
                knowledge_projection.extend(
                    (
                        AliasInput(
                            node_id=knowledge_id,
                            alias=alias,
                            scope=scope,
                            evidence_id=alias_evidence_id,
                            confidence=confidence,
                        ),
                        EvidenceInput(
                            evidence_id=alias_evidence_id,
                            source_type="seed",
                            source_id=knowledge.source_ref,
                            excerpt=alias,
                            source_version=knowledge.source_version,
                            captured_at=now,
                        ),
                    )
                )
            description_evidence_id = f"{evidence_base_id}:description"
            knowledge_projection.extend(
                (
                    DescriptionInput(
                        node_id=knowledge_id,
                        text=searchable,
                        language="zh",
                        kind="genesis_knowledge",
                        evidence_id=description_evidence_id,
                        confidence=confidence,
                    ),
                    EvidenceInput(
                        evidence_id=description_evidence_id,
                        source_type="seed",
                        source_id=knowledge.source_ref,
                        excerpt=knowledge.content,
                        source_version=knowledge.source_version,
                        captured_at=now,
                    ),
                )
            )
            self._record_assertion(
                storage,
                AssertionInput(
                    self_id,
                    predicate,
                    object_node_id=knowledge_id,
                    epistemic_status=epistemic_status,
                    confidence=confidence,
                    importance=knowledge.importance,
                    evidence_ids=(assertion_evidence_id,),
                ),
                EvidenceInput(
                    evidence_id=assertion_evidence_id,
                    source_type="seed",
                    source_id=knowledge.source_ref,
                    excerpt=knowledge.content,
                    source_version=knowledge.source_version,
                    captured_at=now,
                ),
            )

        episode_node_ids: dict[str, str] = {}
        episode_source_ids: dict[str, str] = {}
        episode_source_versions: dict[str, str] = {}
        for sequence_index, seed in enumerate(bundle.episode_seeds):
            episode_id = (
                f"{EPISODE_NODE_PREFIX}{safe_elfie}:{safe_component(seed.seed_id)}"
            )
            event_id = f"{EVENT_NODE_PREFIX}{safe_elfie}:{safe_component(seed.seed_id)}"
            episode_node_ids[seed.seed_id] = event_id
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
            receipt = storage.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"{manifest_id}:episode:{seed.seed_id}",
                    occurred_from=seed.occurred_from,
                    occurred_to=seed.occurred_to,
                    occurrence_precision=precision,
                    content_text=seed.content,
                    summary_text=seed.result or seed.impact or seed.content[:240],
                    event_kind="genesis_personal_episode",
                    source_refs=(source_ref,),
                    source_event_ids=(event_id,),
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
                        "person_ids": list(seed.person_ids),
                        "predecessor_ids": list(seed.predecessor_ids),
                        "related_ids": list(seed.related_ids),
                        "sequence_index": sequence_index,
                    },
                )
            )
            evidence_id = (
                f"genesis:evidence:episode:{safe_elfie}:{safe_component(seed.seed_id)}"
            )
            mentions: list[MentionInput] = [
                MentionInput(
                    episode_id=episode_id,
                    surface_text=seed.content[:120],
                    node_id=event_id,
                    resolution_state="resolved",
                    role="event",
                    confidence=1.0,
                )
            ]
            assertions: list[AssertionInput] = [
                AssertionInput(
                    event_id,
                    "involves",
                    object_node_id=self_id,
                    confidence=1.0,
                    importance=seed.importance,
                    evidence_ids=(evidence_id,),
                ),
                AssertionInput(
                    self_id,
                    "experienced",
                    object_node_id=event_id,
                    confidence=1.0,
                    importance=seed.importance,
                    evidence_ids=(evidence_id,),
                ),
            ]
            for place_key in seed.place_ids:
                place_node = place_node_ids.get(place_key)
                if place_node is None:
                    continue
                mentions.append(
                    MentionInput(
                        episode_id=episode_id,
                        surface_text=place_labels.get(place_key, place_key),
                        node_id=place_node,
                        resolution_state="resolved",
                        role="place",
                        confidence=1.0,
                    )
                )
                assertions.append(
                    AssertionInput(
                        event_id,
                        "at",
                        object_node_id=place_node,
                        confidence=1.0,
                        importance=seed.importance,
                        evidence_ids=(evidence_id,),
                    )
                )
            for person_key in seed.person_ids:
                person_node = person_node_ids.get(person_key)
                if person_node is None:
                    continue
                mentions.append(
                    MentionInput(
                        episode_id=episode_id,
                        surface_text=person_labels.get(person_key, person_key),
                        node_id=person_node,
                        resolution_state="resolved",
                        role="person",
                        confidence=1.0,
                    )
                )
                assertions.append(
                    AssertionInput(
                        event_id,
                        "involves",
                        object_node_id=person_node,
                        confidence=1.0,
                        importance=seed.importance,
                        evidence_ids=(evidence_id,),
                    )
                )
            if seed.impact:
                assertions.append(
                    AssertionInput(
                        event_id,
                        "influences",
                        object_node_id=self_id,
                        context=seed.impact,
                        confidence=1.0,
                        importance=seed.importance,
                        evidence_ids=(evidence_id,),
                    )
                )
            for predecessor_id in seed.predecessor_ids:
                predecessor_event = episode_node_ids.get(predecessor_id)
                if predecessor_event is not None:
                    assertions.append(
                        AssertionInput(
                            predecessor_event,
                            "causes",
                            object_node_id=event_id,
                            confidence=1.0,
                            importance=seed.importance,
                            evidence_ids=(evidence_id,),
                        )
                    )
            aliases = tuple(
                AliasInput(
                    node_id=event_id,
                    alias=alias,
                    scope=scope,
                    evidence_id=evidence_id,
                    confidence=1.0,
                )
                for alias in dict.fromkeys((*seed.aliases, *seed.retrieval_terms))
            )
            description = "；".join(
                item for item in (seed.result, seed.feeling, seed.impact) if item
            )
            storage.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput(
                            node_id=event_id,
                            node_type="event",
                            canonical_label=seed.content[:120],
                            description=description or seed.content,
                            scope=scope,
                            confidence=1.0,
                            importance=seed.importance,
                            retention_profile="genesis",
                            properties={
                                "seed_id": seed.seed_id,
                                "temporal_label": seed.temporal_label,
                                "life_stage": seed.life_stage,
                                "source_ref": seed.source_ref,
                                "source_version": seed.source_version,
                                "result": seed.result,
                                "feeling": seed.feeling,
                                "impact": seed.impact,
                                "sequence_index": sequence_index,
                            },
                        ),
                    ),
                    aliases=aliases,
                    mentions=tuple(mentions),
                    assertions=tuple(assertions),
                    evidence=(
                        EvidenceInput(
                            evidence_id=evidence_id,
                            source_type="episode",
                            source_id=episode_id,
                            excerpt=seed.content,
                            source_version=seed.source_version,
                            source_sha256=receipt.content_sha256,
                            captured_at=now,
                        ),
                    ),
                )
            )
            node_ids.extend((episode_id, event_id))

        # Alias and description indexes are attached to the first real source
        # Episode; no synthetic source record is introduced for an index.
        projection_values = (
            *place_projection,
            *person_projection,
            *knowledge_projection,
        )
        if projection_values and bundle.episode_seeds:
            first_episode_id = (
                f"{EPISODE_NODE_PREFIX}{safe_elfie}:"
                f"{safe_component(bundle.episode_seeds[0].seed_id)}"
            )
            storage.apply_consolidation(
                ConsolidationProjection(
                    episode_id=first_episode_id,
                    aliases=tuple(
                        item
                        for item in projection_values
                        if isinstance(item, AliasInput)
                    ),
                    descriptions=tuple(
                        item
                        for item in projection_values
                        if isinstance(item, DescriptionInput)
                    ),
                    evidence=tuple(
                        item
                        for item in projection_values
                        if isinstance(item, EvidenceInput)
                    ),
                )
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
            self._record_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "relationship",
                    object_node_id=target_node,
                    context=f"{relationship.direction}:{relationship.role}",
                    epistemic_status=(
                        "known" if relationship.certainty == "high" else "believed"
                    ),
                    confidence=max(relationship.initial_trust, 0.5),
                    importance=relationship.importance,
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

        marker_id = f"{GENESIS_RECEIPT_PREFIX}{elfie_id}"
        output_node_ids = (*node_ids, marker_id)
        if output_node_ids != tuple(manifest.output_ids):
            raise GenesisValidationError("Genesis 实际输出 ID 与 Manifest 声明不一致")
        self._upsert_node(
            storage,
            NodeInput(
                node_id=marker_id,
                node_type="genesis_commit_receipt",
                canonical_label="Genesis commit receipt",
                scope=scope,
                status="active",
                confidence=1.0,
                importance=0.0,
                retention_profile="stable",
                properties={
                    "genesis_kind": "commit_receipt",
                    "manifest_id": manifest_id,
                    "compiler_version": manifest.compiler_version,
                    "schema_version": manifest.schema_version,
                    "content_hash": manifest.content_hash,
                    "idempotency_key_digest": key_digest,
                    "output_ids_hash": inventory_hash,
                    "status": "committed",
                    "recall_eligible": False,
                    "node_ids": list(output_node_ids),
                    "output_ids": list(manifest.output_ids),
                    "committed_at": now,
                },
            ),
        )
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
    ) -> tuple[
        dict[str, str],
        dict[str, str],
        list[AliasInput | DescriptionInput | EvidenceInput],
    ]:
        safe_elfie = safe_component(bundle.profile_draft.profile.identity.elfie_id)
        place_node_ids: dict[str, str] = {}
        place_labels: dict[str, str] = {}
        projection: list[AliasInput | DescriptionInput | EvidenceInput] = []
        self_id = f"{SELF_NODE_PREFIX}{safe_elfie}"
        for place in bundle.place_seeds:
            node_id = (
                f"{PLACE_NODE_PREFIX}{safe_elfie}:{safe_component(place.place_id)}"
            )
            place_node_ids[place.place_id] = node_id
            place_labels[place.place_id] = place.label
            self._upsert_node(
                storage,
                NodeInput(
                    node_id=node_id,
                    node_type="place",
                    canonical_label=place.label,
                    description=place.description or None,
                    scope=scope,
                    status="active",
                    confidence=1.0,
                    importance=0.8,
                    properties={
                        "entity_type": "place",
                        "place_id": place.place_id,
                        "kind": place.kind,
                        "parent_id": place.parent_id,
                        "visibility": place.visibility,
                        "source_ref": place.source_ref,
                    },
                ),
            )
            evidence_id = (
                f"genesis:evidence:place:{safe_elfie}:{safe_component(place.place_id)}"
            )
            self._record_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "about",
                    object_node_id=node_id,
                    confidence=1.0,
                    importance=0.8,
                ),
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="seed",
                    source_id=place.source_ref or place.place_id,
                    excerpt=place.label,
                    source_version=bundle.manifest.compiler_version,
                    captured_at=now,
                ),
            )
            for index, alias in enumerate(dict.fromkeys(place.aliases)):
                alias_evidence_id = f"{evidence_id}:alias:{index}"
                projection.extend(
                    (
                        AliasInput(
                            node_id=node_id,
                            alias=alias,
                            scope=scope,
                            evidence_id=alias_evidence_id,
                            confidence=1.0,
                        ),
                        EvidenceInput(
                            evidence_id=alias_evidence_id,
                            source_type="seed",
                            source_id=place.source_ref or place.place_id,
                            excerpt=alias,
                            source_version=bundle.manifest.compiler_version,
                            captured_at=now,
                        ),
                    )
                )
            if place.description:
                description_evidence_id = f"{evidence_id}:description"
                projection.extend(
                    (
                        DescriptionInput(
                            node_id=node_id,
                            text=place.description,
                            language="zh",
                            kind="genesis_place",
                            evidence_id=description_evidence_id,
                            confidence=1.0,
                        ),
                        EvidenceInput(
                            evidence_id=description_evidence_id,
                            source_type="seed",
                            source_id=place.source_ref or place.place_id,
                            excerpt=place.description,
                            source_version=bundle.manifest.compiler_version,
                            captured_at=now,
                        ),
                    )
                )
        return place_node_ids, place_labels, projection


def _marker_node_ids(marker) -> tuple[str, ...]:
    if marker is None:
        return ()
    raw = marker.properties.get("node_ids", ())
    if isinstance(raw, (list, tuple)):
        return tuple(str(value) for value in raw)
    return ()


def _idempotency_key_digest(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise GenesisValidationError("Genesis 幂等键不能为空")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ("GenesisCommitReceipt", "GenesisMemoryCommitter")
