"""Predicate semantics come from the injected ontology snapshot."""

import pytest

from elfie.brain.memory.ontology import MemoryOntologyError
from elfie.brain.memory.predicates import (
    relation_context,
    relation_importance,
    relation_spec,
    resolve_predicate,
)
from infrastructure.persistence.memory.ontology_loader import load_core_memory_ontology


def test_registry_normalizes_aliases_and_keeps_direction_and_symmetry_typed() -> None:
    ontology = load_core_memory_ontology()

    assert resolve_predicate(ontology, "family") == "kin_of"
    assert resolve_predicate(ontology, "friend") == "friend_of"
    assert resolve_predicate(ontology, "owner") == "owned_by"
    assert relation_spec(ontology, "friend_of").symmetric is True
    assert relation_spec(ontology, "parent_of").inverse == "child_of"


def test_relation_salience_comes_from_registry_and_explicit_source_value_wins() -> None:
    ontology = load_core_memory_ontology()

    assert relation_importance(ontology, "friend_of") > relation_importance(
        ontology, "neighbor_of"
    )
    assert relation_importance(ontology, "neighbor_of", 0.91) == pytest.approx(0.91)
    with pytest.raises(MemoryOntologyError, match="unknown or non-active predicate"):
        relation_importance(ontology, "unknown")


def test_relation_context_uses_registered_orientation() -> None:
    ontology = load_core_memory_ontology()

    assert (
        relation_context(
            ontology,
            "episode",
            predicate="friend_of",
            specificity="unspecified",
            role="家人",
        )
        == "relation|episode|symmetry=symmetric|specificity=unspecified|role=家人"
    )
    assert "symmetry=directed" in relation_context(
        ontology, "episode", predicate="parent_of"
    )


def test_predicate_registry_validates_endpoints_qualifiers_and_source() -> None:
    ontology = load_core_memory_ontology()
    ontology.validate_assertion(
        predicate="friend_of",
        subject_type="person",
        object_type="person",
        object_is_literal=False,
        qualifiers=("context",),
        has_source=True,
    )
    with pytest.raises(MemoryOntologyError, match="does not allow subject type"):
        ontology.validate_assertion(
            predicate="friend_of",
            subject_type="concept",
            object_type="person",
            object_is_literal=False,
            has_source=True,
        )
    with pytest.raises(MemoryOntologyError, match="does not allow qualifiers"):
        ontology.validate_assertion(
            predicate="friend_of",
            subject_type="person",
            object_type="person",
            object_is_literal=False,
            qualifiers=("conviction",),
            has_source=True,
        )
    with pytest.raises(MemoryOntologyError, match="requires source Evidence"):
        ontology.validate_assertion(
            predicate="friend_of",
            subject_type="person",
            object_type="person",
            object_is_literal=False,
            has_source=False,
        )
