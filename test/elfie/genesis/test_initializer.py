from dataclasses import replace

import pytest

from elfie.genesis import GenesisMemoryCommitter, GenesisValidationError
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

from .test_contracts import _bundle


def test_genesis_commit_materializes_memory_entities_and_is_idempotent() -> None:
    bundle = _bundle()
    committer = GenesisMemoryCommitter()

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        first = committer.commit(bundle, storage)
        second = committer.commit(bundle, storage)

        assert first.status == "committed"
        assert second.status == "duplicate"
        assert storage.count_nodes("episodic") == 2
        assert (
            storage.get_node("genesis:memory:m-0").metadata["emotion_intensity"] == 0.5
        )
        assert (
            storage.get_node("genesis:self:genesis-check").metadata["is_self"] is True
        )
        assert (
            storage.get_node("genesis:person:seli").metadata["relationship_label"]
            == "mother"
        )
        assert any(
            edge.rel == "relationship"
            for edge in storage.get_edges("genesis:self:genesis-check")
        )
        assert (
            storage.conn.execute("SELECT COUNT(*) FROM known_elfies").fetchone()[0] == 1
        )
        assert storage.conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
        assert storage.conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 3


def test_genesis_rejects_a_second_manifest_for_the_same_elfie() -> None:
    bundle = _bundle()
    conflicting = replace(
        bundle,
        manifest=replace(bundle.manifest, manifest_id="different-manifest"),
    )

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        committer = GenesisMemoryCommitter()
        committer.commit(bundle, storage)
        with pytest.raises(GenesisValidationError, match="另一个 Genesis manifest"):
            committer.commit(conflicting, storage)
