"""Contract tests for the canonical relationship vocabulary."""

import pytest

from elfie.brain.memory.predicates import (
    PREDICATE_REGISTRY_VERSION,
    relation_context,
    relation_importance,
    relation_spec,
    resolve_predicate,
)


def test_relation_registry_normalizes_legacy_words_and_keeps_roles_typed() -> None:
    assert PREDICATE_REGISTRY_VERSION == "memory.predicates.v2"
    assert resolve_predicate("family") == "kin_of"
    assert resolve_predicate("friend") == "friend_of"
    assert resolve_predicate("owner") == "owned_by"
    assert relation_spec("friend_of").symmetric is True
    assert relation_spec("parent_of").inverse == "child_of"


def test_relation_importance_uses_type_prior_without_overriding_source_salience() -> (
    None
):
    assert relation_importance("friend_of") > relation_importance("neighbor_of")
    assert relation_importance("neighbor_of", 0.91) == pytest.approx(0.91)
    assert relation_importance("unknown") == pytest.approx(0.5)


def test_relation_context_is_bounded_and_explicit() -> None:
    assert (
        relation_context(
            "episode",
            symmetric=True,
            specificity="unspecified",
            role="家人",
        )
        == "relation|episode|symmetry=symmetric|specificity=unspecified|role=家人"
    )
