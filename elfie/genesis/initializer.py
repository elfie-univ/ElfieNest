"""Commit the bounded Genesis package into one Elfie's Memory store.

Genesis is deliberately a short-lived hand-off.  This module turns its typed
facts into ordinary memory nodes and graph entities before the runtime is
restored; after that point the normal Memory system owns the resulting data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
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
from elfie.brain.memory.node_types import JsonValue, MemoryNode, NodeTypes
from elfie.profile import ELFARIA_CANON, get_species_canon_for_technical_id

from .contracts import GenesisBundle, GenesisValidationError, validate_genesis_bundle

_GENESIS_MARKER_PREFIX = "genesis:manifest:"
_SELF_NODE_PREFIX = "genesis:self:"
_SELF_MODEL_PREFIX = "genesis:self-model:"
_SELF_FACT_PREFIX = "genesis:knowledge:"
_PLACE_NODE_PREFIX = "genesis:place:"
_PERSON_NODE_PREFIX = "genesis:person:"


@dataclass(frozen=True)
class GenesisCommitReceipt:
    """Evidence that the one-time package was committed or already present."""

    manifest_id: str
    status: Literal["committed", "duplicate"]
    node_ids: tuple[str, ...]


class GenesisMemoryCommitter:
    """Materialize one validated bundle without creating a second source of truth."""

    def commit(
        self, bundle: GenesisBundle, storage: MemoryStorePort
    ) -> GenesisCommitReceipt:
        validate_genesis_bundle(bundle)
        typed_seed_package = bool(bundle.knowledge_seeds or bundle.episode_seeds)
        planned_output_ids: tuple[str, ...] = ()
        if typed_seed_package:
            planned_output_ids = planned_genesis_output_ids(bundle)
            if tuple(bundle.manifest.output_ids) != planned_output_ids:
                raise GenesisValidationError(
                    "InitializationManifest.output_ids 与 Genesis 输出不一致"
                )
            computed_hash = _typed_content_hash(bundle)
            if bundle.manifest.content_hash != computed_hash:
                raise GenesisValidationError(
                    "InitializationManifest.content_hash 与 Genesis 内容不一致"
                )
        elfie_id = bundle.profile_draft.profile.identity.elfie_id
        marker_id = f"{_GENESIS_MARKER_PREFIX}{elfie_id}"
        existing_marker = storage.get_node(marker_id)
        if existing_marker is not None:
            existing_manifest_id = existing_marker.metadata.get("manifest_id")
            if existing_manifest_id != bundle.manifest.manifest_id:
                raise GenesisValidationError(
                    "该 Elfie 已经用另一个 Genesis manifest 初始化，不能覆盖已有生命起点"
                )
            if typed_seed_package:
                expected_hash = bundle.manifest.content_hash or _typed_content_hash(
                    bundle
                )
                existing_hash = existing_marker.metadata.get("content_hash")
                if existing_hash != expected_hash:
                    raise GenesisValidationError(
                        "该 Elfie 的 Genesis manifest 内容与已提交版本不一致"
                    )
            raw_node_ids = existing_marker.metadata.get("node_ids", ())
            existing_node_ids = (
                tuple(str(item) for item in raw_node_ids)
                if isinstance(raw_node_ids, (list, tuple))
                else ()
            )
            return GenesisCommitReceipt(
                manifest_id=bundle.manifest.manifest_id,
                status="duplicate",
                node_ids=existing_node_ids,
            )

        now = datetime.now(timezone.utc).isoformat()
        if typed_seed_package and not _supports_source_first(storage):
            raise TypeError("结构化 Genesis 必须使用 source-first Memory storage")
        if _supports_source_first(storage):
            submission = getattr(storage, "genesis_submission", None)
            if callable(submission):
                submission_id = (
                    bundle.manifest.idempotency_key.strip()
                    or bundle.manifest.manifest_id
                )
                submission_hash = (
                    bundle.manifest.content_hash
                    if typed_seed_package
                    else _legacy_submission_hash(bundle)
                )
                with submission(
                    submission_id=submission_id,
                    manifest_id=bundle.manifest.manifest_id,
                    source_version=bundle.manifest.reference_version,
                    content_sha256=submission_hash,
                    expected_ids=planned_output_ids,
                    elfie_id=elfie_id,
                ) as accepted:
                    if not accepted:
                        return GenesisCommitReceipt(
                            manifest_id=bundle.manifest.manifest_id,
                            status="duplicate",
                            node_ids=(),
                        )
                    return self._commit_source_first(bundle, storage, now)
            return self._commit_source_first(bundle, storage, now)

        profile = bundle.profile_draft.profile
        species = get_species_canon_for_technical_id(profile.identity.species_id)
        self_id = f"{_SELF_NODE_PREFIX}{elfie_id}"
        self_model_id = f"{_SELF_MODEL_PREFIX}{elfie_id}"
        node_ids: list[str] = []

        storage.add_node(
            MemoryNode(
                id=self_id,
                type=NodeTypes.ENTITY.value,
                content=profile.identity.display_name,
                metadata={
                    "entity_type": "elfie",
                    "elfie_id": elfie_id,
                    "display_name": profile.identity.display_name,
                    "species": species.display_name,
                    "species_canon_id": species.canon_id,
                    "is_self": True,
                    "relationship_label": "self",
                    "genesis_manifest_id": bundle.manifest.manifest_id,
                    "personality_big_five": bundle.personality_seed.big_five.model_dump(),
                    "norms": list(bundle.personality_seed.norms),
                    "behavior_anchors": list(bundle.personality_seed.behavior_anchors),
                    "sensory_biases": list(bundle.personality_seed.sensory_biases),
                },
                created_at=now,
                updated_at=now,
            )
        )
        node_ids.append(self_id)

        storage.add_node(
            MemoryNode(
                id=self_model_id,
                type=NodeTypes.KNOWLEDGE.value,
                content=bundle.self_model_seed.identity_summary,
                metadata={
                    "genesis_kind": "self_model",
                    "genesis_manifest_id": bundle.manifest.manifest_id,
                    "recall_eligible": False,
                    "source": "genesis:self_model",
                    "source_event_ids": [self_model_id],
                    "known_facts": list(bundle.self_model_seed.known_facts),
                    "unknown_facts": list(bundle.self_model_seed.unknown_facts),
                    "knowledge_scope": list(bundle.self_model_seed.knowledge_scope),
                    "species_knowledge": list(bundle.self_model_seed.species_knowledge),
                },
                created_at=now,
                updated_at=now,
            )
        )
        node_ids.append(self_model_id)
        storage.add_edge(self_id, self_model_id, "about", weight=1.0)

        for index, fact in enumerate(bundle.self_model_seed.known_facts):
            fact_id = f"{_SELF_FACT_PREFIX}{_safe_component(elfie_id)}:{index}"
            source_event_id = f"genesis:fact:{_safe_component(elfie_id)}:{index}"
            storage.add_node(
                MemoryNode(
                    id=fact_id,
                    type=NodeTypes.KNOWLEDGE.value,
                    content=fact,
                    metadata={
                        "genesis_kind": "knowledge_fact",
                        "genesis_manifest_id": bundle.manifest.manifest_id,
                        "source": "genesis:self_model",
                        "source_event_ids": [source_event_id],
                        "recall_eligible": True,
                        "certainty": "high",
                        "status": "active",
                        "knowledge_scope": list(bundle.self_model_seed.knowledge_scope),
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            node_ids.append(fact_id)
            storage.add_edge(self_id, fact_id, "about", weight=1.0)

        place_ids = _write_place_nodes(bundle, storage, now)
        node_ids.extend(place_ids)
        for place_id in place_ids:
            storage.add_edge(self_id, place_id, "about", weight=1.0)

        for seed in bundle.memory_seeds:
            memory_id = f"genesis:memory:{_safe_component(seed.seed_id)}"
            storage.add_node(
                MemoryNode(
                    id=memory_id,
                    type=NodeTypes.EPISODIC.value,
                    content=seed.content,
                    metadata={
                        "genesis_manifest_id": bundle.manifest.manifest_id,
                        "genesis_seed_id": seed.seed_id,
                        "source": seed.source,
                        "certainty": seed.certainty,
                        "emotion": seed.emotional_tone,
                        "emotion_intensity": seed.intensity,
                        "intensity": seed.intensity,
                        "importance": seed.intensity,
                        "recall_count": 0,
                        "timestamp": now,
                        "consolidated": False,
                        "status": "active",
                        "source_event_ids": [
                            f"genesis:memory:{_safe_component(seed.seed_id)}"
                        ],
                        "recall_eligible": True,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            node_ids.append(memory_id)
            storage.add_edge(memory_id, self_id, "involves", weight=1.0)
            storage.add_edge(memory_id, place_ids[-1], "about", weight=0.85)

        for relationship in bundle.relationship_seeds:
            person_id = (
                f"{_PERSON_NODE_PREFIX}{_safe_component(relationship.person_id)}"
            )
            storage.add_node(
                MemoryNode(
                    id=person_id,
                    type=NodeTypes.ENTITY.value,
                    content=relationship.display_name,
                    metadata={
                        "entity_type": "person",
                        "person_id": relationship.person_id,
                        "relationship_label": relationship.role,
                        "closeness_score": relationship.initial_trust,
                        "trust_score": relationship.initial_trust,
                        "importance_score": relationship.importance,
                        "is_owner": relationship.role == "earth_household",
                        "shared_facts": list(relationship.shared_facts),
                        "unknown_facts": list(relationship.unknown_facts),
                        "genesis_manifest_id": bundle.manifest.manifest_id,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            node_ids.append(person_id)
            storage.add_edge(
                self_id,
                person_id,
                "relationship",
                weight=relationship.initial_trust,
            )

        storage.add_node(
            MemoryNode(
                id=marker_id,
                type=NodeTypes.KNOWLEDGE.value,
                content="Genesis initialization manifest",
                metadata={
                    "genesis_kind": "manifest",
                    "manifest_id": bundle.manifest.manifest_id,
                    "reference_version": bundle.manifest.reference_version,
                    "canon_version": bundle.manifest.canon_version,
                    "species_version": bundle.manifest.species_version,
                    "status": "committed",
                    "recall_eligible": False,
                    "source_event_ids": [marker_id],
                    "node_ids": list(node_ids),
                    "committed_at": now,
                },
                created_at=now,
                updated_at=now,
            )
        )
        node_ids.append(marker_id)
        return GenesisCommitReceipt(
            manifest_id=bundle.manifest.manifest_id,
            status="committed",
            node_ids=tuple(node_ids),
        )

    def _commit_source_first(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        now: str,
    ) -> GenesisCommitReceipt:
        """Materialize Genesis through the target Episode/graph contract.

        Approved Genesis material is still ordinary Memory: seed Episodes keep
        the complete story, while sourced graph assertions provide immediate
        identity and relationship lookup.  This path deliberately avoids the
        legacy ``MemoryNode`` compatibility writer, which otherwise creates a
        second node with the same identifier as an Episode.
        """
        if bundle.knowledge_seeds or bundle.episode_seeds:
            return self._commit_typed_source_first(bundle, storage, now)

        profile = bundle.profile_draft.profile
        elfie_id = profile.identity.elfie_id
        species = get_species_canon_for_technical_id(profile.identity.species_id)
        manifest_id = bundle.manifest.manifest_id
        node_ids: list[str] = []

        self_id = f"{_SELF_NODE_PREFIX}{elfie_id}"
        self_model_id = f"{_SELF_MODEL_PREFIX}{elfie_id}"
        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=self_id,
                node_type="elfie",
                canonical_label=profile.identity.display_name,
                description=bundle.personality_seed.self_description,
                properties={
                    "entity_type": "elfie",
                    "elfie_id": elfie_id,
                    "display_name": profile.identity.display_name,
                    "species": species.display_name,
                    "species_canon_id": species.canon_id,
                    "is_self": True,
                    "relationship_label": "self",
                    "genesis_manifest_id": manifest_id,
                    "personality_big_five": bundle.personality_seed.big_five.model_dump(),
                    "norms": list(bundle.personality_seed.norms),
                    "behavior_anchors": list(bundle.personality_seed.behavior_anchors),
                    "sensory_biases": list(bundle.personality_seed.sensory_biases),
                },
            ),
        )
        node_ids.append(self_id)

        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=self_model_id,
                node_type="self_model",
                canonical_label=bundle.self_model_seed.identity_summary,
                description=bundle.self_model_seed.identity_summary,
                properties={
                    "genesis_kind": "self_model",
                    "genesis_manifest_id": manifest_id,
                    "recall_eligible": False,
                    "source": "genesis:self_model",
                    "source_event_ids": [self_model_id],
                    "known_facts": list(bundle.self_model_seed.known_facts),
                    "unknown_facts": list(bundle.self_model_seed.unknown_facts),
                    "knowledge_scope": list(bundle.self_model_seed.knowledge_scope),
                    "species_knowledge": list(bundle.self_model_seed.species_knowledge),
                },
            ),
        )
        node_ids.append(self_model_id)
        self._record_target_assertion(
            storage,
            AssertionInput(
                self_id,
                "about",
                object_node_id=self_model_id,
                confidence=1.0,
                support_score=1.0,
            ),
            EvidenceInput(
                evidence_id=f"genesis:evidence:self-model:{elfie_id}",
                source_type="seed",
                source_id=self_model_id,
                excerpt=bundle.self_model_seed.identity_summary,
                source_version=bundle.manifest.reference_version,
                captured_at=now,
            ),
        )

        for index, fact in enumerate(bundle.self_model_seed.known_facts):
            fact_id = f"{_SELF_FACT_PREFIX}{_safe_component(elfie_id)}:{index}"
            source_event_id = f"genesis:fact:{_safe_component(elfie_id)}:{index}"
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=fact_id,
                    node_type="knowledge",
                    canonical_label=fact,
                    description=fact,
                    confidence=1.0,
                    properties={
                        "genesis_kind": "knowledge_fact",
                        "genesis_manifest_id": manifest_id,
                        "source": "genesis:self_model",
                        "source_event_ids": [source_event_id],
                        "recall_eligible": True,
                        "certainty": "high",
                        "knowledge_scope": list(bundle.self_model_seed.knowledge_scope),
                    },
                ),
            )
            node_ids.append(fact_id)
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "about",
                    object_node_id=fact_id,
                    confidence=1.0,
                    support_score=1.0,
                ),
                EvidenceInput(
                    evidence_id=f"genesis:evidence:fact:{_safe_component(elfie_id)}:{index}",
                    source_type="seed",
                    source_id=source_event_id,
                    excerpt=fact,
                    source_version=bundle.manifest.reference_version,
                    captured_at=now,
                ),
            )

        place_ids = self._write_target_places(bundle, storage, manifest_id)
        node_ids.extend(place_ids)
        for place_id in place_ids:
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "about",
                    object_node_id=place_id,
                    confidence=1.0,
                    support_score=1.0,
                ),
                EvidenceInput(
                    evidence_id=f"genesis:evidence:place:{place_id}",
                    source_type="seed",
                    source_id=place_id,
                    excerpt=f"Genesis place {place_id}",
                    source_version=bundle.manifest.canon_version,
                    captured_at=now,
                ),
            )

        for relationship in bundle.relationship_seeds:
            person_id = (
                f"{_PERSON_NODE_PREFIX}{_safe_component(relationship.person_id)}"
            )
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=person_id,
                    node_type="person",
                    canonical_label=relationship.display_name,
                    importance=relationship.importance,
                    properties={
                        "entity_type": "person",
                        "person_id": relationship.person_id,
                        "relationship_label": relationship.role,
                        "closeness_score": relationship.initial_trust,
                        "trust_score": relationship.initial_trust,
                        "importance_score": relationship.importance,
                        "is_owner": relationship.role == "earth_household",
                        "shared_facts": list(relationship.shared_facts),
                        "unknown_facts": list(relationship.unknown_facts),
                        "genesis_manifest_id": manifest_id,
                    },
                ),
            )
            node_ids.append(person_id)
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "relationship",
                    object_node_id=person_id,
                    confidence=relationship.initial_trust,
                    importance=relationship.importance,
                    support_score=relationship.initial_trust,
                ),
                EvidenceInput(
                    evidence_id=f"genesis:evidence:relationship:{relationship.person_id}",
                    source_type="seed",
                    source_id=relationship.person_id,
                    excerpt=f"{relationship.display_name}: {relationship.role}",
                    source_version=bundle.manifest.reference_version,
                    captured_at=now,
                ),
            )

        for seed in bundle.memory_seeds:
            episode_id = f"genesis:memory:{_safe_component(seed.seed_id)}"
            source_ref = SourceReference(
                source_id=seed.seed_id,
                source_kind=seed.source,
            )
            episode_receipt = storage.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"genesis:{manifest_id}:{seed.seed_id}",
                    occurred_from=now,
                    content_text=seed.content,
                    event_kind="genesis_memory_seed",
                    source_refs=(source_ref,),
                    source_event_ids=(episode_id,),
                    importance=seed.intensity,
                    emotion=seed.emotional_tone,
                    emotion_intensity=seed.intensity,
                    metadata={
                        "genesis_manifest_id": manifest_id,
                        "genesis_seed_id": seed.seed_id,
                        "source": seed.source,
                        "certainty": seed.certainty,
                        "recall_eligible": True,
                    },
                )
            )
            event_id = f"genesis:event:{_safe_component(seed.seed_id)}"
            projection_nodes = (
                NodeInput(
                    node_id=event_id,
                    node_type="event",
                    canonical_label=seed.content[:120],
                    description=seed.content,
                    confidence=1.0,
                    properties={
                        "genesis_manifest_id": manifest_id,
                        "genesis_seed_id": seed.seed_id,
                        "episode_id": episode_id,
                    },
                ),
            )
            evidence_id = f"genesis:evidence:episode:{_safe_component(seed.seed_id)}"
            storage.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=projection_nodes,
                    mentions=(
                        MentionInput(
                            episode_id=episode_id,
                            surface_text=seed.content[:120],
                            node_id=event_id,
                            resolution_state="resolved",
                            role="event",
                            confidence=1.0,
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            event_id,
                            "involves",
                            object_node_id=self_id,
                            confidence=1.0,
                            support_score=1.0,
                            evidence_ids=(evidence_id,),
                        ),
                    ),
                    evidence=(
                        EvidenceInput(
                            evidence_id=evidence_id,
                            source_type="episode",
                            source_id=episode_id,
                            excerpt=seed.content,
                            source_version=bundle.manifest.reference_version,
                            source_sha256=episode_receipt.content_sha256,
                            captured_at=now,
                        ),
                    ),
                )
            )
            node_ids.append(episode_id)
            node_ids.append(event_id)

        marker_id = f"{_GENESIS_MARKER_PREFIX}{elfie_id}"
        node_ids_for_marker = tuple(node_ids)
        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=marker_id,
                node_type="genesis_manifest",
                canonical_label="Genesis initialization manifest",
                properties={
                    "genesis_kind": "manifest",
                    "manifest_id": manifest_id,
                    "reference_version": bundle.manifest.reference_version,
                    "canon_version": bundle.manifest.canon_version,
                    "species_version": bundle.manifest.species_version,
                    "status": "committed",
                    "recall_eligible": False,
                    "source_event_ids": [marker_id],
                    "node_ids": list(node_ids_for_marker),
                    "committed_at": now,
                },
            ),
        )
        node_ids.append(marker_id)
        return GenesisCommitReceipt(
            manifest_id=manifest_id,
            status="committed",
            node_ids=tuple(node_ids),
        )

    def _commit_typed_source_first(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        now: str,
    ) -> GenesisCommitReceipt:
        """Commit the structured World Canon and personal life graph.

        The implementation deliberately uses only the existing Episode and
        graph operations.  Public facts retain direct ``seed`` evidence from
        the versioned Canon, while each personal Episode remains a normal
        closed source record.  IDs are namespaced by Elfie so two offline
        adoptions never share people, places, or memories merely because they
        share a world.
        """

        profile = bundle.profile_draft.profile
        elfie_id = profile.identity.elfie_id
        safe_elfie = _safe_component(elfie_id)
        manifest_id = bundle.manifest.manifest_id
        scope = f"elfie:{safe_elfie}"
        species = get_species_canon_for_technical_id(profile.identity.species_id)
        # Resolve every referenced Canon place before the first durable write;
        # malformed typed packages therefore fail closed instead of leaving a
        # partially projected graph when used directly with a Memory store.
        place_specs = _typed_place_specs(bundle)
        node_ids: list[str] = []

        self_id = f"{_SELF_NODE_PREFIX}{safe_elfie}"
        self_model_id = f"{_SELF_MODEL_PREFIX}{safe_elfie}"
        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=self_id,
                node_type="elfie",
                canonical_label=profile.identity.display_name,
                description=bundle.personality_seed.self_description,
                scope=scope,
                confidence=1.0,
                properties={
                    "entity_type": "elfie",
                    "elfie_id": elfie_id,
                    "display_name": profile.identity.display_name,
                    "species": species.display_name,
                    "species_canon_id": species.canon_id,
                    "is_self": True,
                    "relationship_label": "self",
                    "genesis_manifest_id": manifest_id,
                    "genesis_namespace": bundle.manifest.namespace or scope,
                    "canon_version": bundle.manifest.canon_version,
                    "personality_big_five": bundle.personality_seed.big_five.model_dump(),
                    "norms": list(bundle.personality_seed.norms),
                    "behavior_anchors": list(bundle.personality_seed.behavior_anchors),
                    "sensory_biases": list(bundle.personality_seed.sensory_biases),
                },
            ),
        )
        node_ids.append(self_id)

        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=self_model_id,
                node_type="self_model",
                canonical_label=bundle.self_model_seed.identity_summary,
                description=bundle.self_model_seed.identity_summary,
                scope=scope,
                confidence=1.0,
                properties={
                    "genesis_kind": "self_model",
                    "genesis_manifest_id": manifest_id,
                    "recall_eligible": False,
                    "source": "genesis:self_model",
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
        self._record_target_assertion(
            storage,
            AssertionInput(
                self_id,
                "about",
                object_node_id=self_model_id,
                confidence=1.0,
                support_score=1.0,
            ),
            EvidenceInput(
                evidence_id=f"genesis:evidence:self-model:{safe_elfie}",
                source_type="seed",
                source_id=f"self-model:{safe_elfie}",
                excerpt=bundle.self_model_seed.identity_summary,
                source_version=bundle.manifest.reference_version,
                captured_at=now,
            ),
        )

        # The canonical place anchors are private projections, not a shared
        # graph.  Their labels and aliases are sourced from the bounded Canon
        # map; the projections are attached to a real Episode below so the
        # existing consolidation API remains the only alias/description path.
        place_node_ids: dict[str, str] = {}
        place_labels: dict[str, str] = {}
        place_aliases: list[AliasInput] = []
        place_descriptions: list[DescriptionInput] = []
        place_evidence: list[EvidenceInput] = []
        for place_key, label, place_kind, extra, aliases in place_specs:
            place_id = f"{_PLACE_NODE_PREFIX}{safe_elfie}:{_safe_component(place_key)}"
            place_node_ids[place_key] = place_id
            place_labels[place_key] = label
            place_source_ref = f"canon:{bundle.manifest.canon_version}#{place_key}"
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=place_id,
                    node_type="place",
                    canonical_label=label,
                    description=(
                        str(extra["description"])
                        if extra.get("description") is not None
                        else None
                    ),
                    scope=scope,
                    confidence=1.0,
                    properties={
                        "entity_type": "place",
                        "place_id": place_key,
                        "place_type": place_kind,
                        "genesis_manifest_id": manifest_id,
                        "source_kind": "canon",
                        "source_ref": place_source_ref,
                        **extra,
                    },
                ),
            )
            node_ids.append(place_id)
            about_evidence_id = (
                f"genesis:evidence:place:{safe_elfie}:{_safe_component(place_key)}"
            )
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "about",
                    object_node_id=place_id,
                    confidence=1.0,
                    support_score=1.0,
                ),
                EvidenceInput(
                    evidence_id=about_evidence_id,
                    source_type="seed",
                    source_id=place_source_ref,
                    excerpt=label,
                    source_version=bundle.manifest.canon_version,
                    captured_at=now,
                ),
            )
            for alias_index, alias in enumerate(aliases):
                alias_evidence_id = (
                    f"genesis:evidence:place-alias:{safe_elfie}:"
                    f"{_safe_component(place_key)}:{alias_index}"
                )
                place_aliases.append(
                    AliasInput(
                        node_id=place_id,
                        alias=alias,
                        scope=scope,
                        evidence_id=alias_evidence_id,
                        confidence=1.0,
                    )
                )
                place_evidence.append(
                    EvidenceInput(
                        evidence_id=alias_evidence_id,
                        source_type="seed",
                        source_id=place_source_ref,
                        excerpt=alias,
                        source_version=bundle.manifest.canon_version,
                        captured_at=now,
                    )
                )
            if extra.get("description"):
                description_evidence_id = (
                    f"genesis:evidence:place-description:{safe_elfie}:"
                    f"{_safe_component(place_key)}"
                )
                place_descriptions.append(
                    DescriptionInput(
                        node_id=place_id,
                        text=str(extra["description"]),
                        language="zh",
                        kind="genesis_place",
                        evidence_id=description_evidence_id,
                        confidence=1.0,
                    )
                )
                place_evidence.append(
                    EvidenceInput(
                        evidence_id=description_evidence_id,
                        source_type="seed",
                        source_id=place_source_ref,
                        excerpt=str(extra["description"]),
                        source_version=bundle.manifest.canon_version,
                        captured_at=now,
                    )
                )

        person_node_ids: dict[str, str] = {}
        person_labels: dict[str, str] = {}
        relationship_aliases: list[AliasInput] = []
        relationship_descriptions: list[DescriptionInput] = []
        relationship_evidence: list[EvidenceInput] = []
        for relationship in bundle.relationship_seeds:
            target_key = relationship.object_id or relationship.person_id
            if relationship.object_kind == "place":
                # A place relationship is represented by the Canon place
                # anchor above; never create a second person-shaped node for it.
                continue
            # Preserve the existing owner lookup contract inside the private
            # workspace; all other people remain explicitly Elfie-namespaced.
            person_id = (
                f"{_PERSON_NODE_PREFIX}{_safe_component(target_key)}"
                if target_key.startswith("owner-")
                else f"{_PERSON_NODE_PREFIX}{safe_elfie}:{_safe_component(target_key)}"
            )
            person_node_ids[target_key] = person_id
            person_node_ids[relationship.person_id] = person_id
            person_labels[target_key] = relationship.display_name
            person_labels[relationship.person_id] = relationship.display_name
            relationship_description = "；".join(
                item
                for item in (
                    f"关系角色：{relationship.role}",
                    *relationship.shared_facts,
                    *(f"未知：{item}" for item in relationship.unknown_facts),
                )
                if item
            )
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=person_id,
                    node_type=(
                        "person"
                        if relationship.object_kind == "person"
                        else relationship.object_kind
                    ),
                    canonical_label=relationship.display_name,
                    description=relationship_description or None,
                    scope=scope,
                    confidence=max(relationship.initial_trust, relationship.importance),
                    importance=relationship.importance,
                    properties={
                        "entity_type": relationship.object_kind,
                        "person_id": relationship.person_id,
                        "relationship_id": relationship.stable_relationship_id,
                        "relationship_label": relationship.role,
                        "direction": relationship.direction,
                        "familiarity": relationship.familiarity,
                        "closeness_score": relationship.initial_trust,
                        "trust_score": relationship.initial_trust,
                        "importance_score": relationship.importance,
                        "is_owner": relationship.role == "earth_household",
                        "shared_facts": list(relationship.shared_facts),
                        "unknown_facts": list(relationship.unknown_facts),
                        "episode_ids": list(relationship.episode_ids),
                        "genesis_manifest_id": manifest_id,
                        "source_kind": relationship.source,
                        "source_ref": relationship.source_ref,
                        "source_version": relationship.source_version,
                        "certainty": relationship.certainty,
                    },
                ),
            )
            if person_id not in node_ids:
                node_ids.append(person_id)
            for alias_index, alias in enumerate(
                dict.fromkeys((*relationship.aliases, *relationship.retrieval_terms))
            ):
                alias_evidence_id = (
                    f"genesis:evidence:relationship-alias:{safe_elfie}:"
                    f"{_safe_component(relationship.stable_relationship_id)}:{alias_index}"
                )
                relationship_aliases.append(
                    AliasInput(
                        node_id=person_id,
                        alias=alias,
                        scope=scope,
                        evidence_id=alias_evidence_id,
                        confidence=max(relationship.initial_trust, 0.5),
                    )
                )
                relationship_evidence.append(
                    EvidenceInput(
                        evidence_id=alias_evidence_id,
                        source_type="seed",
                        source_id=relationship.source_ref,
                        excerpt=alias,
                        source_version=relationship.source_version,
                        captured_at=now,
                    )
                )
            if relationship_description:
                description_evidence_id = (
                    f"genesis:evidence:relationship-description:{safe_elfie}:"
                    f"{_safe_component(relationship.stable_relationship_id)}"
                )
                relationship_descriptions.append(
                    DescriptionInput(
                        node_id=person_id,
                        text=relationship_description,
                        language="zh",
                        kind="genesis_relationship",
                        evidence_id=description_evidence_id,
                        confidence=max(relationship.initial_trust, 0.5),
                    )
                )
                relationship_evidence.append(
                    EvidenceInput(
                        evidence_id=description_evidence_id,
                        source_type="seed",
                        source_id=relationship.source_ref,
                        excerpt=relationship_description,
                        source_version=relationship.source_version,
                        captured_at=now,
                    )
                )

        # Public facts use the existing approved-seed evidence path.  Keeping
        # them as graph knowledge (rather than synthetic visible Episodes)
        # preserves the five personal Episodes expected by the runtime while
        # retaining a direct Canon source for every assertion.
        knowledge_aliases: list[AliasInput] = []
        knowledge_descriptions: list[DescriptionInput] = []
        knowledge_evidence: list[EvidenceInput] = []
        for knowledge_seed in bundle.knowledge_seeds:
            knowledge_id = f"{_SELF_FACT_PREFIX}{safe_elfie}:{_safe_component(knowledge_seed.seed_id)}"
            evidence_id = (
                f"genesis:evidence:knowledge:{safe_elfie}:"
                f"{_safe_component(knowledge_seed.seed_id)}"
            )
            recall_eligible = (
                knowledge_seed.status == "active"
                and knowledge_seed.mastery != "unknown"
            )
            searchable_description = "\n".join(
                [
                    knowledge_seed.content,
                    f"[{knowledge_seed.topic}/{knowledge_seed.level}/{knowledge_seed.mastery}]",
                    *knowledge_seed.aliases,
                    *knowledge_seed.retrieval_terms,
                ]
            )
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=knowledge_id,
                    node_type="knowledge",
                    canonical_label=knowledge_seed.content,
                    description=searchable_description,
                    scope=scope,
                    status="active" if recall_eligible else "unresolved",
                    confidence=_certainty_score(knowledge_seed.certainty),
                    importance=knowledge_seed.importance,
                    properties={
                        "genesis_kind": "knowledge_seed",
                        "genesis_manifest_id": manifest_id,
                        "source_kind": knowledge_seed.source,
                        "source_ref": knowledge_seed.source_ref,
                        "source_version": knowledge_seed.source_version,
                        "certainty": knowledge_seed.certainty,
                        "level": knowledge_seed.level,
                        "mastery": knowledge_seed.mastery,
                        "status": knowledge_seed.status,
                        "scope": knowledge_seed.scope,
                        "topic": knowledge_seed.topic,
                        "eligibility": list(knowledge_seed.eligibility),
                        "related_ids": list(knowledge_seed.related_ids),
                        "recall_eligible": recall_eligible,
                        "source_event_ids": [knowledge_seed.source_ref],
                    },
                ),
            )
            node_ids.append(knowledge_id)
            for alias in (*knowledge_seed.aliases, *knowledge_seed.retrieval_terms):
                knowledge_aliases.append(
                    AliasInput(
                        node_id=knowledge_id,
                        alias=alias,
                        scope=scope,
                        evidence_id=evidence_id,
                        confidence=_certainty_score(knowledge_seed.certainty),
                    )
                )
            knowledge_descriptions.append(
                DescriptionInput(
                    node_id=knowledge_id,
                    text=(
                        f"[{knowledge_seed.topic}/{knowledge_seed.level}/"
                        f"{knowledge_seed.mastery}] {knowledge_seed.content}"
                    ),
                    language="zh",
                    kind="genesis_knowledge",
                    evidence_id=evidence_id,
                    confidence=_certainty_score(knowledge_seed.certainty),
                )
            )
            knowledge_evidence.append(
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="seed",
                    source_id=knowledge_seed.source_ref,
                    excerpt=knowledge_seed.content,
                    source_version=knowledge_seed.source_version,
                    captured_at=now,
                )
            )
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "knows" if recall_eligible else "knows_boundary",
                    object_node_id=knowledge_id,
                    epistemic_status=(
                        "known"
                        if knowledge_seed.mastery == "known"
                        else "uncertain"
                        if knowledge_seed.status == "unknown-boundary"
                        or knowledge_seed.mastery == "unknown"
                        else "believed"
                    ),
                    confidence=_certainty_score(knowledge_seed.certainty),
                    importance=knowledge_seed.importance,
                    support_score=_mastery_score(knowledge_seed.mastery),
                    evidence_ids=(evidence_id,),
                ),
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="seed",
                    source_id=knowledge_seed.source_ref,
                    excerpt=knowledge_seed.content,
                    source_version=knowledge_seed.source_version,
                    captured_at=now,
                ),
            )

        # Personal Episodes are written in declared order, so predecessor and
        # causal assertions can only point to already materialized events.
        episode_node_ids: dict[str, str] = {}
        for sequence_index, episode_seed in enumerate(bundle.episode_seeds):
            episode_id = (
                f"genesis:episode:{safe_elfie}:{_safe_component(episode_seed.seed_id)}"
            )
            event_id = (
                f"genesis:event:{safe_elfie}:{_safe_component(episode_seed.seed_id)}"
            )
            episode_node_ids[episode_seed.seed_id] = event_id
            source_ref = SourceReference(
                source_id=episode_seed.source_ref,
                source_kind=episode_seed.source,
                locator=episode_seed.seed_id,
            )
            if (
                episode_seed.occurred_from is None
                and episode_seed.occurred_to is not None
            ):
                raise GenesisValidationError(
                    "EpisodeSeed.occurred_to 不能在缺少 occurred_from 时单独提供"
                )
            occurrence_precision: Literal["exact", "range", "unknown"] = (
                "unknown"
                if episode_seed.occurred_from is None
                else "range"
                if episode_seed.occurred_to is not None
                else "exact"
            )
            episode_receipt = storage.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"{manifest_id}:episode:{episode_seed.seed_id}",
                    occurred_from=episode_seed.occurred_from,
                    occurred_to=episode_seed.occurred_to,
                    occurrence_precision=occurrence_precision,
                    content_text=episode_seed.content,
                    summary_text=(
                        episode_seed.result
                        or episode_seed.impact
                        or episode_seed.content[:240]
                    ),
                    event_kind="genesis_personal_episode",
                    source_refs=(source_ref,),
                    source_event_ids=(event_id,),
                    source_version=episode_seed.source_version,
                    importance=episode_seed.importance,
                    emotion=episode_seed.emotional_tone,
                    emotion_intensity=episode_seed.emotion_intensity,
                    metadata={
                        "genesis_manifest_id": manifest_id,
                        "genesis_seed_id": episode_seed.seed_id,
                        "source_kind": episode_seed.source,
                        "source_ref": episode_seed.source_ref,
                        "source_version": episode_seed.source_version,
                        "certainty": episode_seed.certainty,
                        "temporal_label": episode_seed.temporal_label,
                        "life_stage": episode_seed.life_stage,
                        "result": episode_seed.result,
                        "feeling": episode_seed.feeling,
                        "impact": episode_seed.impact,
                        "place_ids": list(episode_seed.place_ids),
                        "person_ids": list(episode_seed.person_ids),
                        "predecessor_ids": list(episode_seed.predecessor_ids),
                        "causal_links": list(episode_seed.causal_links),
                        "related_ids": list(episode_seed.related_ids),
                        "sequence_index": sequence_index,
                        "recall_eligible": True,
                        "written_at": now,
                    },
                )
            )
            node_ids.append(episode_id)
            evidence_id = f"genesis:evidence:episode:{safe_elfie}:{_safe_component(episode_seed.seed_id)}"
            mentions: list[MentionInput] = [
                MentionInput(
                    episode_id=episode_id,
                    surface_text=episode_seed.content[:120],
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
                    importance=episode_seed.importance,
                    support_score=1.0,
                    evidence_ids=(evidence_id,),
                ),
                AssertionInput(
                    self_id,
                    "experienced",
                    object_node_id=event_id,
                    confidence=1.0,
                    importance=episode_seed.importance,
                    support_score=1.0,
                    evidence_ids=(evidence_id,),
                ),
            ]
            for place_key in episode_seed.place_ids:
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
                        importance=episode_seed.importance,
                        support_score=1.0,
                        evidence_ids=(evidence_id,),
                    )
                )
            for person_key in episode_seed.person_ids:
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
                        importance=episode_seed.importance,
                        support_score=1.0,
                        evidence_ids=(evidence_id,),
                    )
                )
            if episode_seed.impact:
                assertions.append(
                    AssertionInput(
                        event_id,
                        "influences",
                        object_node_id=self_id,
                        context=episode_seed.impact,
                        confidence=1.0,
                        importance=episode_seed.importance,
                        support_score=1.0,
                        evidence_ids=(evidence_id,),
                    )
                )
            for predecessor_id in episode_seed.predecessor_ids:
                predecessor_event = episode_node_ids.get(predecessor_id)
                if predecessor_event is None:
                    continue
                assertions.append(
                    AssertionInput(
                        predecessor_event,
                        "causes",
                        object_node_id=event_id,
                        confidence=1.0,
                        importance=episode_seed.importance,
                        support_score=1.0,
                        evidence_ids=(evidence_id,),
                    )
                )
            episode_aliases: tuple[AliasInput, ...] = tuple(
                AliasInput(
                    node_id=event_id,
                    alias=alias,
                    scope=scope,
                    evidence_id=evidence_id,
                    confidence=1.0,
                )
                for alias in (*episode_seed.aliases, *episode_seed.retrieval_terms)
            )
            description = "；".join(
                item
                for item in (
                    episode_seed.result,
                    episode_seed.feeling,
                    episode_seed.impact,
                )
                if item
            )
            storage.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput(
                            node_id=event_id,
                            node_type="event",
                            canonical_label=episode_seed.content[:120],
                            description=description or episode_seed.content,
                            scope=scope,
                            confidence=_certainty_score(episode_seed.certainty),
                            importance=episode_seed.importance,
                            properties={
                                "genesis_manifest_id": manifest_id,
                                "genesis_seed_id": episode_seed.seed_id,
                                "episode_id": episode_id,
                                "temporal_label": episode_seed.temporal_label,
                                "life_stage": episode_seed.life_stage,
                                "source_ref": episode_seed.source_ref,
                                "source_version": episode_seed.source_version,
                                "result": episode_seed.result,
                                "feeling": episode_seed.feeling,
                                "impact": episode_seed.impact,
                                "related_ids": list(episode_seed.related_ids),
                                "sequence_index": sequence_index,
                            },
                        ),
                    ),
                    aliases=episode_aliases,
                    mentions=tuple(mentions),
                    assertions=tuple(assertions),
                    evidence=(
                        EvidenceInput(
                            evidence_id=evidence_id,
                            source_type="episode",
                            source_id=episode_id,
                            excerpt=episode_seed.content,
                            source_version=episode_seed.source_version,
                            source_sha256=episode_receipt.content_sha256,
                            captured_at=now,
                        ),
                    ),
                )
            )
            node_ids.append(event_id)

        # Alias/description projections are attached to the first personal
        # Episode so they use the existing consolidation API without creating
        # an extra visible synthetic Episode for the Canon snapshot.
        if episode_node_ids and (
            knowledge_aliases
            or relationship_aliases
            or place_aliases
            or knowledge_descriptions
            or relationship_descriptions
            or place_descriptions
        ):
            first_seed_id = next(iter(episode_node_ids))
            first_episode_id = (
                f"genesis:episode:{safe_elfie}:{_safe_component(first_seed_id)}"
            )
            storage.apply_consolidation(
                ConsolidationProjection(
                    episode_id=first_episode_id,
                    aliases=tuple(
                        knowledge_aliases + relationship_aliases + place_aliases
                    ),
                    descriptions=tuple(
                        knowledge_descriptions
                        + relationship_descriptions
                        + place_descriptions
                    ),
                    evidence=tuple(
                        knowledge_evidence + relationship_evidence + place_evidence
                    ),
                )
            )

        # Relationship assertions are emitted after all Episodes exist, so a
        # relation can be grounded in a shared Episode when one is supplied.
        for relationship in bundle.relationship_seeds:
            target_key = relationship.object_id or relationship.person_id
            target_node = person_node_ids.get(target_key) or place_node_ids.get(
                target_key
            )
            if target_node is None:
                continue
            related_episode = next(
                (
                    episode_node_ids[item]
                    for item in relationship.episode_ids
                    if item in episode_node_ids
                ),
                None,
            )
            source_id = (
                next(
                    (
                        f"genesis:episode:{safe_elfie}:{_safe_component(item)}"
                        for item in relationship.episode_ids
                        if item in episode_node_ids
                    ),
                    None,
                )
                or relationship.source_ref
            )
            relation_evidence_id = (
                f"genesis:evidence:relationship:{safe_elfie}:"
                f"{_safe_component(relationship.stable_relationship_id)}"
            )
            self._record_target_assertion(
                storage,
                AssertionInput(
                    self_id,
                    "relationship",
                    object_node_id=target_node,
                    context=f"{relationship.direction}:{relationship.role}",
                    epistemic_status="known"
                    if relationship.certainty == "high"
                    else "believed",
                    confidence=max(relationship.initial_trust, 0.5),
                    importance=relationship.importance,
                    support_score=relationship.initial_trust,
                ),
                EvidenceInput(
                    evidence_id=relation_evidence_id,
                    source_type="episode" if related_episode else "seed",
                    source_id=source_id,
                    excerpt=(
                        f"{relationship.display_name}: {relationship.role}; "
                        f"{'; '.join(relationship.shared_facts)}"
                    ),
                    source_version=relationship.source_version,
                    captured_at=now,
                ),
            )

        marker_id = f"{_GENESIS_MARKER_PREFIX}{elfie_id}"
        output_node_ids = (*node_ids, marker_id)
        content_hash = _typed_content_hash(bundle)
        self._upsert_target_node(
            storage,
            NodeInput(
                node_id=marker_id,
                node_type="genesis_manifest",
                canonical_label="Genesis initialization manifest",
                scope=scope,
                confidence=1.0,
                properties={
                    "genesis_kind": "manifest",
                    "manifest_id": manifest_id,
                    "namespace": bundle.manifest.namespace or scope,
                    "generator_version": bundle.manifest.generator_version,
                    "schema_version": bundle.manifest.schema_version,
                    "reference_version": bundle.manifest.reference_version,
                    "canon_version": bundle.manifest.canon_version,
                    "species_version": bundle.manifest.species_version,
                    "master_seed": bundle.manifest.master_seed,
                    "content_hash": bundle.manifest.content_hash or content_hash,
                    "idempotency_key": bundle.manifest.idempotency_key or manifest_id,
                    "status": "committed",
                    "recall_eligible": False,
                    "source_event_ids": [marker_id],
                    "node_ids": list(output_node_ids),
                    "output_ids": list(bundle.manifest.output_ids or output_node_ids),
                    "committed_at": now,
                },
            ),
        )
        return GenesisCommitReceipt(
            manifest_id=manifest_id,
            status="committed",
            node_ids=output_node_ids,
        )

    @staticmethod
    def _upsert_target_node(storage: MemoryStorePort, node: NodeInput) -> None:
        upsert = getattr(storage, "upsert_node_record", None)
        if not callable(upsert):
            raise TypeError("source-first Memory storage lacks node upsert")
        upsert(node)

    @staticmethod
    def _record_target_assertion(
        storage: MemoryStorePort,
        assertion: AssertionInput,
        evidence: EvidenceInput,
    ) -> None:
        record = getattr(storage, "record_sourced_assertion", None)
        if not callable(record):
            raise TypeError("source-first Memory storage lacks sourced assertions")
        record(assertion, evidence)

    def _write_target_places(
        self,
        bundle: GenesisBundle,
        storage: MemoryStorePort,
        manifest_id: str,
    ) -> list[str]:
        profile = bundle.profile_draft.profile
        origin = profile.identity.origin
        nodes = (
            (
                f"{_PLACE_NODE_PREFIX}elfaria",
                ELFARIA_CANON.display_name,
                "home_world",
                {"world_id": origin.home_world_id},
            ),
            (
                f"{_PLACE_NODE_PREFIX}{_safe_component(origin.home_region_id)}",
                ELFARIA_CANON.known_region_name,
                "home_region",
                {"region_id": origin.home_region_id, "world_id": origin.home_world_id},
            ),
            (
                f"{_PLACE_NODE_PREFIX}{_safe_component(origin.arrival_base_id)}",
                ELFARIA_CANON.earth_home_name,
                "earth_home",
                {
                    "base_id": origin.arrival_base_id,
                    "world_id": "earth",
                    "role": ELFARIA_CANON.earth_home_role,
                },
            ),
        )
        ids: list[str] = []
        for node_id, label, place_type, extra in nodes:
            self._upsert_target_node(
                storage,
                NodeInput(
                    node_id=node_id,
                    node_type="place",
                    canonical_label=label,
                    properties={
                        "entity_type": "place",
                        "place_type": place_type,
                        "genesis_manifest_id": manifest_id,
                        **extra,
                    },
                ),
            )
            ids.append(node_id)
        return ids


def _write_place_nodes(
    bundle: GenesisBundle,
    storage: MemoryStorePort,
    now: str,
) -> list[str]:
    profile = bundle.profile_draft.profile
    origin = profile.identity.origin
    nodes = (
        (
            f"{_PLACE_NODE_PREFIX}elfaria",
            ELFARIA_CANON.display_name,
            "home_world",
            {"world_id": origin.home_world_id},
        ),
        (
            f"{_PLACE_NODE_PREFIX}{_safe_component(origin.home_region_id)}",
            ELFARIA_CANON.known_region_name,
            "home_region",
            {"region_id": origin.home_region_id, "world_id": origin.home_world_id},
        ),
        (
            f"{_PLACE_NODE_PREFIX}{_safe_component(origin.arrival_base_id)}",
            ELFARIA_CANON.earth_home_name,
            "earth_home",
            {
                "base_id": origin.arrival_base_id,
                "world_id": "earth",
                "role": ELFARIA_CANON.earth_home_role,
            },
        ),
    )
    ids: list[str] = []
    for node_id, content, place_type, extra in nodes:
        storage.add_node(
            MemoryNode(
                id=node_id,
                type=NodeTypes.ENTITY.value,
                content=content,
                metadata={
                    "entity_type": "place",
                    "place_type": place_type,
                    "genesis_manifest_id": bundle.manifest.manifest_id,
                    **extra,
                },
                created_at=now,
                updated_at=now,
            )
        )
        ids.append(node_id)
    return ids


def _safe_component(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in value
    )


def _certainty_score(certainty: str) -> float:
    return {"high": 1.0, "medium": 0.75, "low": 0.5}.get(certainty, 0.5)


def _mastery_score(mastery: str) -> float:
    return {
        "known": 1.0,
        "partial": 0.75,
        "heard": 0.5,
        "unknown": 0.0,
    }.get(mastery, 0.5)


def _typed_content_hash(bundle: GenesisBundle) -> str:
    """Hash all deterministic seed content, excluding commit timestamps.

    The marker uses this digest to distinguish a true idempotent replay from a
    caller that reuses a manifest ID with changed aliases, sources, mastery or
    relationship edges.  The adoption compiler computes the same payload
    before constructing the immutable bundle, so the declared manifest hash
    and the committer's replay check are identical.  Tuple ordering is
    intentional: it is part of the declared Genesis sequence and must not be
    normalized away.
    """

    payload = {
        "knowledge": [asdict(seed) for seed in bundle.knowledge_seeds],
        "episodes": [asdict(seed) for seed in bundle.episode_seeds],
        "relationships": [asdict(relation) for relation in bundle.relationship_seeds],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _legacy_submission_hash(bundle: GenesisBundle) -> str:
    """Hash the compatibility bundle when no typed seed content is present."""
    payload = {
        "manifest_id": bundle.manifest.manifest_id,
        "memory_seeds": [asdict(seed) for seed in bundle.memory_seeds],
        "relationships": [asdict(seed) for seed in bundle.relationship_seeds],
        "self_model": asdict(bundle.self_model_seed),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def planned_genesis_output_ids(bundle: GenesisBundle) -> tuple[str, ...]:
    """Return the deterministic durable IDs emitted by a typed Genesis run.

    The adoption compiler records these IDs in ``InitializationManifest``
    before the first write.  Keeping the calculation beside the committer
    prevents the compiler and the source-first projection from drifting into
    different output inventories.
    """

    if not (bundle.knowledge_seeds or bundle.episode_seeds):
        return ()
    profile = bundle.profile_draft.profile
    elfie_id = profile.identity.elfie_id
    safe_elfie = _safe_component(elfie_id)
    output: list[str] = [
        f"{_SELF_NODE_PREFIX}{safe_elfie}",
        f"{_SELF_MODEL_PREFIX}{safe_elfie}",
    ]
    output.extend(
        f"{_PLACE_NODE_PREFIX}{safe_elfie}:{_safe_component(place_key)}"
        for place_key, _label, _kind, _extra, _aliases in _typed_place_specs(bundle)
    )
    seen_people: set[str] = set()
    for relationship in bundle.relationship_seeds:
        if relationship.object_kind == "place":
            continue
        target_key = relationship.object_id or relationship.person_id
        if target_key in seen_people:
            continue
        seen_people.add(target_key)
        person_id = (
            f"{_PERSON_NODE_PREFIX}{_safe_component(target_key)}"
            if target_key.startswith("owner-")
            else f"{_PERSON_NODE_PREFIX}{safe_elfie}:{_safe_component(target_key)}"
        )
        output.append(person_id)
    output.extend(
        f"{_SELF_FACT_PREFIX}{safe_elfie}:{_safe_component(seed.seed_id)}"
        for seed in bundle.knowledge_seeds
    )
    for seed in bundle.episode_seeds:
        output.append(f"genesis:episode:{safe_elfie}:{_safe_component(seed.seed_id)}")
        output.append(f"genesis:event:{safe_elfie}:{_safe_component(seed.seed_id)}")
    output.append(f"{_GENESIS_MARKER_PREFIX}{elfie_id}")
    return tuple(output)


def _typed_place_specs(
    bundle: GenesisBundle,
) -> tuple[tuple[str, str, str, dict[str, JsonValue], tuple[str, ...]], ...]:
    """Return only the approved world/place anchors referenced by this bundle."""

    profile = bundle.profile_draft.profile
    origin = profile.identity.origin
    base: dict[str, tuple[str, str, dict[str, JsonValue], tuple[str, ...]]] = {
        "elfaria": (
            ELFARIA_CANON.display_name,
            "home_world",
            {"world_id": origin.home_world_id},
            ("Elfaria", "母星"),
        ),
        "mistyville": (
            ELFARIA_CANON.known_region_name,
            "home_region",
            {"region_id": origin.home_region_id, "world_id": origin.home_world_id},
            ("迷雾镇", "Mistyville"),
        ),
        "mistyville_square": (
            "迷雾镇公共空间",
            "settlement_shared_space",
            {"parent_id": "mistyville"},
            ("公共空间",),
        ),
        "mistyville_homes": (
            "迷雾镇居住区",
            "settlement_homes",
            {"parent_id": "mistyville"},
            ("居住区", "住处"),
        ),
        "mistyville_learning_house": (
            "迷雾镇学习场所",
            "learning_place",
            {"parent_id": "mistyville"},
            ("学习场所",),
        ),
        "mistyville_waystation": (
            "迷雾镇赴地设施",
            "departure_facility",
            {"parent_id": "mistyville"},
            ("赴地设施", "出发处"),
        ),
        "earth_gateway_station": (
            "地球侧基站",
            "earth_gateway_station",
            {"world_id": "earth", "parent_id": "earth"},
            ("地球基站", "基站"),
        ),
        "elfie_nest": (
            ELFARIA_CANON.earth_home_name,
            "earth_home",
            {
                "base_id": origin.arrival_base_id,
                "world_id": "earth",
                "parent_id": "earth",
                "role": ELFARIA_CANON.earth_home_role,
                "description": ELFARIA_CANON.earth_home_role,
            },
            ("地球的家", "在地球的基地"),
        ),
    }
    requested = {"elfaria", "mistyville", "elfie_nest"}
    for episode in bundle.episode_seeds:
        requested.update(episode.place_ids)
    for relation in bundle.relationship_seeds:
        if relation.object_kind == "place":
            requested.add(relation.object_id or relation.person_id)
    specs: list[tuple[str, str, str, dict[str, JsonValue], tuple[str, ...]]] = []
    for key in sorted(requested):
        if key not in base:
            raise GenesisValidationError(f"Genesis 引用了未批准的地点 ID: {key}")
        label, kind, extra, aliases = base[key]
        specs.append((key, label, kind, dict(extra), aliases))
    return tuple(specs)


def _supports_source_first(storage: MemoryStorePort) -> bool:
    """Detect the target Adapter without widening the Genesis Port contract."""
    return all(
        callable(getattr(storage, name, None))
        for name in (
            "record_episode",
            "apply_consolidation",
            "upsert_node_record",
            "record_sourced_assertion",
        )
    )


__all__ = (
    "GenesisCommitReceipt",
    "GenesisMemoryCommitter",
    "planned_genesis_output_ids",
)
