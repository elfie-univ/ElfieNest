"""The injected ontology is the sole source of Memory node classification."""

import pytest

from elfie.brain.memory.memory_records import NodeInput, memory_node_group
from elfie.brain.memory.ontology import MemoryOntologyError
from infrastructure.persistence.memory.ontology_loader import load_core_memory_ontology


def test_core_ontology_exposes_the_five_reviewed_groups_and_leaf_types() -> None:
    ontology = load_core_memory_ontology()

    assert {
        group.group_id: tuple(
            item.node_type for item in ontology.active_node_types(group.group_id)
        )
        for group in ontology.type_groups
    } == {
        "social_relations": ("elfie", "person", "group"),
        "entities": ("organism", "object", "material"),
        "space_geography": ("cosmic_entity", "place"),
        "events": ("event",),
        "general_knowledge": (
            "concept",
            "claim",
            "theory_or_model",
            "principle_or_law",
            "pattern",
            "rule_or_guideline",
            "method_or_procedure",
            "viewpoint",
        ),
    }


def test_group_is_derived_from_registered_leaf_type_not_stored_on_node() -> None:
    ontology = load_core_memory_ontology()
    node = NodeInput("person-1", "person", "林")

    assert memory_node_group(node.node_type, ontology) == "social_relations"
    assert not hasattr(node, "type_group")


def test_unsupported_and_non_active_types_cannot_be_selected_for_writes() -> None:
    ontology = load_core_memory_ontology()

    with pytest.raises(MemoryOntologyError, match="unsupported Memory node_type"):
        memory_node_group("self_model", ontology)
    with pytest.raises(MemoryOntologyError, match="unsupported Memory node_type"):
        ontology.validate_node_type("made_up_type")
