"""Commit the bounded Genesis package into one Elfie's Memory store.

Genesis is deliberately a short-lived hand-off.  This module turns its typed
facts into ordinary memory nodes and graph entities before the runtime is
restored; after that point the normal Memory system owns the resulting data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    MentionInput,
    NodeInput,
    SourceReference,
)
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.node_types import MemoryNode, NodeTypes
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
        elfie_id = bundle.profile_draft.profile.identity.elfie_id
        marker_id = f"{_GENESIS_MARKER_PREFIX}{elfie_id}"
        existing_marker = storage.get_node(marker_id)
        if existing_marker is not None:
            existing_manifest_id = existing_marker.metadata.get("manifest_id")
            if existing_manifest_id != bundle.manifest.manifest_id:
                raise GenesisValidationError(
                    "该 Elfie 已经用另一个 Genesis manifest 初始化，不能覆盖已有生命起点"
                )
            return GenesisCommitReceipt(
                manifest_id=bundle.manifest.manifest_id,
                status="duplicate",
                node_ids=tuple(existing_marker.metadata.get("node_ids", ())),
            )

        now = datetime.now(timezone.utc).isoformat()
        if _supports_source_first(storage):
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
                        "importance_score": 1.0,
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
                    properties={
                        "entity_type": "person",
                        "person_id": relationship.person_id,
                        "relationship_label": relationship.role,
                        "closeness_score": relationship.initial_trust,
                        "trust_score": relationship.initial_trust,
                        "importance_score": 1.0,
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
                    support_score=relationship.initial_trust,
                ),
                EvidenceInput(
                    evidence_id=f"genesis:evidence:relationship:{relationship.person_id}",
                    source_type="seed",
                    source_id=relationship.person_id,
                    excerpt=f"{relationship.display_name}: {relationship.role}",
                    captured_at=now,
                ),
            )

        for seed in bundle.memory_seeds:
            episode_id = f"genesis:memory:{_safe_component(seed.seed_id)}"
            source_ref = SourceReference(
                source_id=seed.seed_id,
                source_kind=seed.source,
            )
            storage.record_episode(
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


__all__ = ("GenesisCommitReceipt", "GenesisMemoryCommitter")
