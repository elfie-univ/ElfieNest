from dataclasses import replace
from pathlib import Path

import pytest

from app.features.adoption import AcceptedAdoptionReservation
from elfie.brain.memory.memory_records import RecallRequest
from elfie.genesis import GenesisMemoryCommitter, GenesisValidationError
from elfie.genesis.initializer import _safe_component, _typed_content_hash
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
    _genesis_bundle,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def _reservation(elfie_id: str = "00000101") -> AcceptedAdoptionReservation:
    return AcceptedAdoptionReservation(
        elfie_id=elfie_id,
        owner_user_id=7,
        name="第一版精灵",
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=101,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2001-01-01",
    )


def test_typed_genesis_records_story_graph_manifest_and_recall(tmp_path: Path) -> None:
    reservation = _reservation()
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    profile = YamlProfileStoreAdapter(workspace / "profile").load()
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    bundle = _genesis_bundle(reservation, profile, selfhood)

    assert len(bundle.knowledge_seeds) >= 30
    assert len(bundle.episode_seeds) == 5
    assert len(bundle.relationship_seeds) == 13
    assert bundle.manifest.content_hash == _typed_content_hash(bundle)
    assert bundle.manifest.output_ids
    assert bundle.manifest.output_ids[-1] == "genesis:manifest:00000101"

    memory_path = workspace / "memory" / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(memory_path) as storage:
        assert storage.count_nodes("episodic") == 5
        assert storage.count_nodes("person") == 13
        marker = storage.get_node("genesis:manifest:00000101")
        assert marker is not None
        assert len(marker.metadata["output_ids"]) == len(bundle.manifest.output_ids)

        rare = storage.recall(RecallRequest(text="重新约定", lexical_limit=10))
        assert any("shared-space-choice" in item.episode_id for item in rare.episodes)

        unknown = storage.recall(RecallRequest(text="完整地图", lexical_limit=10))
        assert any(
            assertion.predicate == "knows_boundary"
            and assertion.qualifiers.get("epistemic_status") == "uncertain"
            for assertion in unknown.assertions
        )

    # A close/reopen cycle must preserve the same source Episodes and marker.
    with SQLiteMemoryStoreAdapter(memory_path) as reopened:
        assert reopened.count_nodes("episodic") == 5
        assert reopened.get_node("genesis:manifest:00000101") is not None

    adapter.materialize(reservation)
    with SQLiteMemoryStoreAdapter(memory_path) as repeated:
        assert repeated.count_nodes("episodic") == 5
        assert repeated.count_nodes("person") == 13
    adapter.release(reservation.elfie_id)


def test_typed_genesis_propagates_explicit_importance_to_nodes_and_assertions(
    tmp_path: Path,
) -> None:
    reservation = _reservation("00000104")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    profile = YamlProfileStoreAdapter(workspace / "profile").load()
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    bundle = _genesis_bundle(reservation, profile, selfhood)
    customized = replace(
        bundle,
        knowledge_seeds=(
            replace(bundle.knowledge_seeds[0], importance=0.91),
            *bundle.knowledge_seeds[1:],
        ),
        relationship_seeds=(
            replace(bundle.relationship_seeds[0], importance=0.37),
            *bundle.relationship_seeds[1:],
        ),
    )
    customized = replace(
        customized,
        manifest=replace(
            customized.manifest,
            content_hash=_typed_content_hash(customized),
        ),
    )

    with SQLiteMemoryStoreAdapter.in_memory(elfie_id=reservation.elfie_id) as storage:
        GenesisMemoryCommitter().commit(customized, storage)
        knowledge = customized.knowledge_seeds[0]
        knowledge_node_id = (
            f"genesis:knowledge:{reservation.elfie_id}:"
            f"{_safe_component(knowledge.seed_id)}"
        )
        knowledge_node = storage.connection.execute(
            "SELECT importance FROM nodes WHERE node_id=?", (knowledge_node_id,)
        ).fetchone()
        assert knowledge_node is not None
        assert float(knowledge_node[0]) == pytest.approx(knowledge.importance)
        knowledge_assertion = storage.connection.execute(
            """SELECT a.importance
                 FROM assertions AS a
                 JOIN nodes AS n ON n.node_id=a.object_node_id
                WHERE a.subject_node_id=? AND a.predicate='knows'
                  AND n.node_id=?""",
            (f"genesis:self:{reservation.elfie_id}", knowledge_node_id),
        ).fetchone()
        assert knowledge_assertion is not None
        assert float(knowledge_assertion[0]) == pytest.approx(knowledge.importance)

        relationship = customized.relationship_seeds[0]
        person_node_id = (
            f"genesis:person:{reservation.elfie_id}:"
            f"{_safe_component(relationship.person_id)}"
        )
        person_node = storage.connection.execute(
            "SELECT importance FROM nodes WHERE node_id=?", (person_node_id,)
        ).fetchone()
        assert person_node is not None
        assert float(person_node[0]) == pytest.approx(relationship.importance)
        relationship_assertion = storage.connection.execute(
            """SELECT importance FROM assertions
                WHERE subject_node_id=? AND predicate='relationship'
                  AND object_node_id=?""",
            (f"genesis:self:{reservation.elfie_id}", person_node_id),
        ).fetchone()
        assert relationship_assertion is not None
        assert float(relationship_assertion[0]) == pytest.approx(
            relationship.importance
        )

    adapter.release(reservation.elfie_id)


def test_typed_genesis_fails_closed_without_source_first_storage(
    tmp_path: Path,
) -> None:
    reservation = _reservation("00000102")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    profile = YamlProfileStoreAdapter(workspace / "profile").load()
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    bundle = _genesis_bundle(reservation, profile, selfhood)

    class LegacyOnlyStorage:
        def get_node(self, _node_id: str):
            return None

    with pytest.raises(TypeError, match="source-first"):
        GenesisMemoryCommitter().commit(bundle, LegacyOnlyStorage())
    adapter.release(reservation.elfie_id)


def test_typed_genesis_rejects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    reservation = _reservation("00000103")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    profile = YamlProfileStoreAdapter(workspace / "profile").load()
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    bundle = _genesis_bundle(reservation, profile, selfhood)
    from dataclasses import replace

    tampered = replace(
        bundle,
        manifest=replace(bundle.manifest, content_hash="0" * 64),
    )
    # The real workspace already contains the valid marker; a fresh in-memory
    # store proves the hash is checked before any source-first write.
    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        with pytest.raises(GenesisValidationError, match="content_hash"):
            GenesisMemoryCommitter().commit(tampered, storage)
        assert storage.count_nodes() == 0
    adapter.release(reservation.elfie_id)
