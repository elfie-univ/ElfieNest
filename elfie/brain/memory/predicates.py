"""Versioned predicate vocabulary for source-grounded Memory assertions."""

from __future__ import annotations

from typing import Final, Mapping

PREDICATE_REGISTRY_VERSION: Final[str] = "memory.predicates.v1"

# Keep the first registry deliberately small and explicit.  A new relation is
# added by versioning this registry; model output is never allowed to create a
# new active predicate implicitly.
PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "about",
        "at",
        "causal",
        "causes",
        "caused_by",
        "acquaintance",
        "emotional",
        "experienced",
        "felt",
        "family",
        "generalizes",
        "has_condition",
        "implies",
        "involves",
        "influences",
        "is",
        "knows",
        "knows_boundary",
        "likes",
        "dislikes",
        "part_of",
        "prefers",
        "preferred_name",
        "relationship",
        "references",
        "related_to",
        "subtype_of",
        "supports",
        "temporal",
        "used_in",
        "friend",
        "owner",
    }
)

ALIASES: Final[Mapping[str, str]] = {
    "causal": "causes",
    "cause": "causes",
    "dislike": "dislikes",
    "favorite": "prefers",
    "involved_in": "involves",
    "like": "likes",
    "relates_to": "related_to",
}


class UnknownPredicateError(ValueError):
    """A proposal used a predicate outside the versioned vocabulary."""


def resolve_predicate(value: str) -> str:
    """Return the canonical predicate or raise a deterministic validation error."""
    normalized = "_".join(value.strip().casefold().replace("-", "_").split())
    normalized = ALIASES.get(normalized, normalized)
    if normalized not in PREDICATES:
        raise UnknownPredicateError(
            f"unknown predicate for registry {PREDICATE_REGISTRY_VERSION}: {value}"
        )
    return normalized


__all__ = [
    "ALIASES",
    "PREDICATE_REGISTRY_VERSION",
    "PREDICATES",
    "UnknownPredicateError",
    "resolve_predicate",
]
