from dataclasses import replace
from pathlib import Path

import pytest

from elfie.brain.memory.memory_records import RecallRequest
from elfie.genesis import (
    GenesisMemoryCommitter,
    GenesisValidationError,
    genesis_content_hash,
)
from elfie.genesis.serialization import safe_component
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

from .test_contracts import _compilation


def test_typed_genesis_materializes_story_graph_and_reopens(tmp_path: Path) -> None:
    compilation = _compilation("00000101")
    arrival = next(
        episode
        for episode in compilation.bundle.episode_seeds
        if episode.theme_id == "arrival-nest"
    )
    assert arrival.place_ids == ("elfie_nest",)
    arrival_base = next(
        place
        for place in compilation.bundle.place_seeds
        if place.place_id == "elfie_nest"
    )
    assert arrival_base.label == "ElfieNest"
    assert arrival_base.kind == "earth_home"
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    adapter.stage(compilation)
    workspace = Path(adapter.publish("00000101"))

    profile = YamlProfileStoreAdapter(workspace / "profile").load()
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    assert profile.to_dict() == compilation.profile.to_dict()
    assert selfhood["identity_core"]["elfie_id"] == "00000101"

    memory_path = workspace / "memory" / "knowledge.sqlite"
    expected_episode_count = len(compilation.bundle.knowledge_seeds) + len(
        compilation.bundle.episode_seeds
    )
    expected_relationship_node_counts = {
        kind: sum(
            relationship.object_kind == kind
            for relationship in compilation.bundle.relationship_seeds
        )
        + (kind == "elfie")
        for kind in ("person", "elfie", "group")
    }
    with SQLiteMemoryStoreAdapter(memory_path, elfie_id="00000101") as storage:
        assert storage.count_episodes() == expected_episode_count
        for kind, expected_count in expected_relationship_node_counts.items():
            assert storage.count_graph_nodes(kind) == expected_count
        marker = storage.get_graph_node("genesis:receipt:00000101")
        assert marker is not None
        assert marker.properties["output_ids"] == list(
            compilation.bundle.manifest.output_ids
        )
        rare = storage.recall(RecallRequest(text="重新约定", lexical_limit=10))
        assert any("shared-space-choice" in item.episode_id for item in rare.episodes)

        identity_seed = next(
            seed
            for seed in compilation.bundle.knowledge_seeds
            if "Elfaria 是精灵生活的星球" in seed.content
        )
        identity = storage.recall(
            RecallRequest(text="Elfaria 是精灵生活的星球", lexical_limit=10)
        )
        assert any(
            item.episode_id.endswith(
                f":knowledge:{safe_component(identity_seed.seed_id)}"
            )
            for item in identity.episodes
        )
        assert not any(
            assertion.predicate in {"knows", "knows_boundary"}
            for assertion in identity.assertions
        )

        unknown_seed = next(
            seed
            for seed in compilation.bundle.knowledge_seeds
            if "没有覆盖完整星球地图" in seed.content
        )
        unknown = storage.recall(RecallRequest(text="完整星球地图", lexical_limit=10))
        assert any(
            item.episode_id.endswith(
                f":knowledge:{safe_component(unknown_seed.seed_id)}"
            )
            and "完整星球地图" in item.excerpt
            for item in unknown.episodes
        )

    # A close/reopen cycle must preserve the same source Episodes and marker.
    with SQLiteMemoryStoreAdapter(memory_path, elfie_id="00000101") as reopened:
        assert reopened.count_episodes() == expected_episode_count
        assert reopened.get_graph_node("genesis:receipt:00000101") is not None

    adapter.finalize("00000101")


def test_typed_genesis_propagates_importance_to_nodes_and_assertions() -> None:
    compilation = _compilation("00000104")
    bundle = compilation.bundle
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
            content_hash=genesis_content_hash(customized),
        ),
    )

    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="00000104") as storage:
        GenesisMemoryCommitter().commit(customized, storage)
        knowledge_episode = storage.get_episode(
            "genesis:episode:00000104:knowledge:"
            f"{safe_component(customized.knowledge_seeds[0].seed_id)}"
        )
        assert knowledge_episode is not None
        assert knowledge_episode.importance == pytest.approx(0.91)
        first_relationship = customized.relationship_seeds[0]
        relationship_target = (
            first_relationship.object_id or first_relationship.person_id
        )
        person_id = f"genesis:person:00000104:{safe_component(relationship_target)}"
        person = storage.get_graph_node(person_id)
        assert person is not None
        assert person.importance == pytest.approx(0.37)


def test_typed_genesis_fails_closed_without_source_first_storage() -> None:
    bundle = _compilation("00000102").bundle

    class LegacyOnlyStorage:
        pass

    with pytest.raises(TypeError, match="source-first"):
        GenesisMemoryCommitter().commit(bundle, LegacyOnlyStorage())


def test_typed_genesis_rejects_a_tampered_manifest_hash() -> None:
    bundle = _compilation("00000103").bundle
    tampered = replace(
        bundle,
        manifest=replace(bundle.manifest, content_hash="0" * 64),
    )

    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="00000103") as storage:
        with pytest.raises(GenesisValidationError, match="content_hash"):
            GenesisMemoryCommitter().commit(tampered, storage)
        assert storage.count_memory_records() == 0
