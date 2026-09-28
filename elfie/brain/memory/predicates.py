"""Small operations on the injected Memory ontology predicate vocabulary."""

from __future__ import annotations

from elfie.brain.memory.ontology import (
    MemoryOntologyError,
    MemoryOntologySnapshot,
    PredicateSpec,
)


class UnknownPredicateError(MemoryOntologyError):
    """A proposal used a predicate outside the active ontology snapshot."""


def resolve_predicate(ontology: MemoryOntologySnapshot, value: str) -> str:
    """Resolve an alias or canonical predicate from the injected snapshot."""
    try:
        return ontology.resolve_predicate(value)
    except MemoryOntologyError as error:
        raise UnknownPredicateError(str(error)) from error


def relation_spec(
    ontology: MemoryOntologySnapshot,
    predicate: str,
) -> PredicateSpec | None:
    """Return active registered relation semantics, or None for read display."""
    try:
        return ontology.predicate_spec(predicate)
    except MemoryOntologyError:
        return None


def relation_importance(
    ontology: MemoryOntologySnapshot,
    predicate: str,
    supplied: float | None = None,
) -> float:
    """Use registry salience unless a sourced explicit value is supplied."""
    spec = ontology.predicate_spec(predicate)
    if supplied is None:
        return spec.salience
    return min(1.0, max(0.0, float(supplied)))


def relation_context(
    ontology: MemoryOntologySnapshot,
    source: str,
    *,
    predicate: str,
    specificity: str | None = None,
    role: str | None = None,
) -> str:
    """Produce the bounded relationship qualifier using registered direction."""
    if not source.strip():
        raise ValueError("relationship context source must not be blank")
    semantics = ontology.predicate_spec(predicate)
    values = [
        "relation",
        source.strip(),
        f"symmetry={'symmetric' if semantics.symmetric else 'directed'}",
    ]
    if specificity:
        values.append(f"specificity={specificity.strip()}")
    if role:
        values.append(f"role={role.strip()}")
    return "|".join(values)


__all__ = (
    "UnknownPredicateError",
    "relation_context",
    "relation_importance",
    "relation_spec",
    "resolve_predicate",
)
