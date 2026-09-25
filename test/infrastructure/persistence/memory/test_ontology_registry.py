"""Core and root-global ontology snapshots stay typed and revisioned."""

from pathlib import Path

import pytest

from elfie.brain.memory.ontology import (
    MemoryOntologyError,
    NodeTypeSpec,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_bundled_document,
)
from infrastructure.persistence.configuration.documents import ConfigDocumentId
from infrastructure.persistence.memory.ontology_loader import (
    load_core_memory_ontology,
    load_memory_ontology_snapshot,
)
from infrastructure.persistence.memory.sqlite_ontology_registry import (
    SQLiteMemoryOntologyRegistryAdapter,
)


def test_dynamic_extensions_share_one_registry_per_product_data_root(
    tmp_path: Path,
) -> None:
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"
    core_document = load_bundled_document(ConfigDocumentId.MEMORY_ONTOLOGY)

    initial = load_memory_ontology_snapshot(data_home=first_home)
    assert initial.registry_revision == 0
    registry_path = first_home / "memory" / "ontology.sqlite"
    with SQLiteMemoryOntologyRegistryAdapter(registry_path, core_document) as registry:
        assert (
            registry.propose_node_type(
                NodeTypeSpec(
                    node_type="personal_role",
                    label="个人角色",
                    group_id="social_relations",
                    color="#b892ff",
                    status="candidate",
                    core=False,
                )
            )
            == 1
        )
        candidate = registry.snapshot()
        with pytest.raises(MemoryOntologyError, match="candidate, not writable"):
            candidate.validate_node_type("personal_role")
        assert (
            registry.set_extension_status("node_type", "personal_role", "active") == 2
        )

    shared = load_memory_ontology_snapshot(data_home=first_home)
    isolated = load_memory_ontology_snapshot(data_home=second_home)
    assert shared.revision == "memory.ontology.v1+registry:2"
    assert shared.group_for_node_type("personal_role") == "social_relations"
    assert isolated.revision == "memory.ontology.v1+registry:0"
    assert "personal_role" not in {item.node_type for item in isolated.node_types}

    with SQLiteMemoryOntologyRegistryAdapter(registry_path, core_document) as registry:
        assert (
            registry.set_extension_status("node_type", "personal_role", "deprecated")
            == 3
        )
        deprecated = registry.snapshot()
    with pytest.raises(MemoryOntologyError, match="deprecated, not writable"):
        deprecated.validate_node_type("personal_role")


def test_extensions_cannot_override_core_definitions(tmp_path: Path) -> None:
    core_document = load_bundled_document(ConfigDocumentId.MEMORY_ONTOLOGY)
    registry_path = tmp_path / "ontology.sqlite"
    with SQLiteMemoryOntologyRegistryAdapter(registry_path, core_document) as registry:
        with pytest.raises(MemoryOntologyError, match="non-core candidate"):
            registry.propose_node_type(
                NodeTypeSpec(
                    node_type="person",
                    label="替代人物",
                    group_id="social_relations",
                    color="#ffffff",
                    status="candidate",
                    core=True,
                )
            )
    assert load_core_memory_ontology().registry_revision == 0
