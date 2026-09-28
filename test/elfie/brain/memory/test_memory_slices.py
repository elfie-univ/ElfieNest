"""The six Memory slices are derived views over registered Nodes and edges."""

import pytest

from elfie.brain.memory.memory_records import (
    AssertionInput,
    MemoryInspectionSnapshot,
    NodeInput,
    RecallAssertion,
    RecallNode,
)
from elfie.brain.memory.ontology import MemoryOntologyError
from elfie.brain.memory.slices import project_memory_slices
from infrastructure.persistence.memory.ontology_loader import load_core_memory_ontology


def _node(node_id: str, node_type: str, *, self_node: bool = False) -> NodeInput:
    properties = {"is_self": True} if self_node else {}
    return NodeInput(node_id, node_type, node_id, properties=properties)


def _edge(
    assertion_id: str,
    subject_id: str,
    predicate: str,
    object_node_id: str,
    *evidence_ids: str,
) -> AssertionInput:
    return AssertionInput(
        subject_id,
        predicate,
        object_node_id=object_node_id,
        evidence_ids=evidence_ids or (f"evidence:{assertion_id}",),
        assertion_id=assertion_id,
    )


def test_six_slices_select_by_group_then_edge_and_extract_cross_group_edges() -> None:
    ontology = load_core_memory_ontology()
    nodes = (
        _node("self", "elfie", self_node=True),
        _node("person", "person"),
        _node("object", "object"),
        _node("place", "place"),
        _node("event", "event"),
        _node("claim", "claim"),
        _node("concept", "concept"),
    )
    assertions = (
        _edge("friend", "self", "friend_of", "person"),
        _edge("stance", "self", "believes", "claim"),
        _edge("knowledge-link", "claim", "implies", "concept"),
        _edge("located", "person", "located_in", "place"),
    )

    slices = project_memory_slices(nodes, assertions, ontology)
    by_group = {item.slice_id: item for item in slices.type_slices}

    assert tuple(by_group) == (
        "social_relations",
        "entities",
        "space_geography",
        "events",
        "general_knowledge",
    )
    assert by_group["social_relations"].assertion_ids == ("friend",)
    assert by_group["general_knowledge"].assertion_ids == ("knowledge-link",)
    assert slices.self_model.node_ids == ("self", "claim")
    assert slices.self_model.assertion_ids == ("stance",)
    # The self slice does not recursively add `concept` through claim -> concept.
    assert "knowledge-link" not in slices.self_model.assertion_ids
    assert slices.cross_group_assertion_ids == ("stance", "located")
    assert slices.write_nodes == nodes
    assert slices.write_assertions == assertions


def test_slice_projection_deduplicates_nodes_and_merges_evidence_for_same_fact() -> (
    None
):
    ontology = load_core_memory_ontology()
    duplicate = _edge("friend", "a", "friend_of", "b", "evidence-a")
    second_source = _edge("friend", "a", "friend_of", "b", "evidence-b")

    slices = project_memory_slices(
        (_node("a", "person"), _node("b", "person"), _node("a", "person")),
        (duplicate, second_source),
        ontology,
    )

    assert tuple(node.node_id for node in slices.write_nodes) == ("a", "b")
    assert len(slices.write_assertions) == 1
    assert slices.write_assertions[0].evidence_ids == ("evidence-a", "evidence-b")
    assert slices.type_slices[0].assertion_ids == ("friend",)


def test_technical_self_model_type_and_unregistered_predicates_are_rejected() -> None:
    ontology = load_core_memory_ontology()

    with pytest.raises(MemoryOntologyError, match="unsupported Memory node_type"):
        project_memory_slices((_node("self-model", "self_model"),), (), ontology)
    with pytest.raises(MemoryOntologyError, match="unknown or non-active predicate"):
        project_memory_slices(
            (_node("a", "person"), _node("b", "person")),
            (_edge("unknown", "a", "invented_relation", "b"),),
            ontology,
        )


def test_self_model_slice_starts_from_the_existing_graph_anchor_without_recursing() -> (
    None
):
    ontology = load_core_memory_ontology()
    graph = MemoryInspectionSnapshot(
        nodes=(
            RecallNode(
                "self", "elfie", "精灵", None, 1.0, properties={"is_self": True}
            ),
            RecallNode("claim", "claim", "命题", None, 1.0),
            RecallNode("concept", "concept", "概念", None, 1.0),
        ),
        assertions=(
            RecallAssertion(
                "stance",
                "self",
                "believes",
                "claim",
                None,
                {},
                "active",
                ("evidence-stance",),
                1.0,
            ),
            RecallAssertion(
                "knowledge-link",
                "claim",
                "implies",
                "concept",
                None,
                {},
                "active",
                ("evidence-link",),
                1.0,
            ),
        ),
    )

    slices = project_memory_slices((), (), ontology, self_model_graph=graph)

    assert slices.self_model.node_ids == ("self", "claim")
    assert slices.self_model.assertion_ids == ("stance",)
