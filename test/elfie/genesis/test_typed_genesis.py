import hashlib
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
    early_home = next(
        episode
        for episode in compilation.bundle.episode_seeds
        if episode.theme_id == "early-home"
    )
    assert "我在家中长大" in early_home.content
    assert "我的家在我的住处" not in early_home.content
    arrival = next(
        episode
        for episode in compilation.bundle.episode_seeds
        if episode.theme_id == "arrival-nest"
    )
    assert {episode.event_kind for episode in compilation.bundle.episode_seeds} <= {
        "activity",
        "conversation",
        "learning",
        "life_event",
        "observation",
        "outing",
        "reflection",
        "unclassified",
    }
    assert early_home.event_kind == "outing"
    assert arrival.event_kind == "life_event"
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
        assert storage.get_graph_node("genesis:receipt:00000101") is None
        submission_id = hashlib.sha256(
            compilation.bundle.manifest.idempotency_key.strip().encode("utf-8")
        ).hexdigest()
        submission = storage.get_genesis_submission(submission_id)
        assert submission is not None
        assert submission.manifest_id == compilation.bundle.manifest.manifest_id
        assert len(submission.expected_ids_hash) == 64
        friend_seed = next(
            episode
            for episode in compilation.bundle.episode_seeds
            if episode.theme_id == "shared-space-choice"
        )
        friend_episode = storage.get_episode(
            f"genesis:episode:00000101:{safe_component(friend_seed.seed_id)}"
        )
        assert friend_episode is not None
        assert "相识" in friend_episode.content_text
        related = storage.recall(RecallRequest(text="相识", lexical_limit=10))
        assert any(
            item.episode_id == friend_episode.episode_id for item in related.episodes
        )

        identity_seed = next(
            seed
            for seed in compilation.bundle.knowledge_seeds
            if "Elfaria 是精灵生活的星球" in seed.content
        )
        knowledge_episode = storage.get_episode(
            "genesis:episode:00000101:knowledge:"
            f"{safe_component(identity_seed.seed_id)}"
        )
        assert knowledge_episode is not None
        assert knowledge_episode.summary_text is None
        search_seed = next(
            seed
            for seed in compilation.bundle.knowledge_seeds
            if seed.aliases or seed.retrieval_terms
        )
        search_term = (search_seed.aliases or search_seed.retrieval_terms)[0]
        search_episode = storage.get_episode(
            f"genesis:episode:00000101:knowledge:{safe_component(search_seed.seed_id)}"
        )
        assert search_episode is not None
        indexed_text = storage.connection.execute(
            "SELECT searchable_text FROM episodes_fts WHERE episode_id=?",
            (search_episode.episode_id,),
        ).fetchone()[0]
        assert search_seed.content in indexed_text
        assert search_term in indexed_text
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

    # A close/reopen cycle preserves semantic Episodes and the submission ledger.
    with SQLiteMemoryStoreAdapter(memory_path, elfie_id="00000101") as reopened:
        assert reopened.count_episodes() == expected_episode_count
        assert reopened.get_graph_node("genesis:receipt:00000101") is None
        assert reopened.get_genesis_submission(submission_id) == submission

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
