"""Tests for the frozen Memory node taxonomy."""

import pytest

from elfie.brain.memory import (
    NodeInput,
    memory_knowledge_kind,
    memory_node_domain,
    resolve_memory_node_type,
)


def test_entity_leaf_types_share_entity_domain_without_collapsing_identity() -> None:
    assert memory_node_domain("elfie") == "entity"
    assert memory_node_domain("person") == "entity"
    assert memory_node_domain("group") == "entity"
    assert resolve_memory_node_type("elfie").kind == "elfie"
    assert resolve_memory_node_type("person").kind == "person"
    assert resolve_memory_node_type("group").kind == "group"


def test_knowledge_subtype_is_explicit_and_pattern_is_not_a_top_level_domain() -> None:
    assert memory_node_domain("knowledge") == "knowledge"
    assert (
        memory_knowledge_kind("knowledge", {"knowledge_kind": "pattern"}) == "pattern"
    )
    assert memory_node_domain("pattern") == "knowledge"
    assert memory_knowledge_kind("pattern") == "pattern"


def test_node_input_rejects_unregistered_semantic_type() -> None:
    with pytest.raises(ValueError, match="unsupported Memory node_type"):
        NodeInput("unknown", "made_up_type", "未知")
