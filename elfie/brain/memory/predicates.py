"""Versioned predicate vocabulary for source-grounded Memory assertions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping, Optional

PREDICATE_REGISTRY_VERSION: Final[str] = "memory.predicates.v2"

# These spellings remain readable for old development rows and fixtures, but
# are not writable by Genesis or Consolidation. They describe an implicit
# knowledge boundary or a generic topic link rather than a useful graph fact.
NON_SEMANTIC_LEGACY_PREDICATES: Final[frozenset[str]] = frozenset(
    {"about", "knows", "knows_boundary", "related_to"}
)

# Keep the registry explicit. Model output is never allowed to create a new
# active predicate implicitly.
PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "about",
        "at",
        "causal",
        "causes",
        "caused_by",
        "acquaintance_of",
        "caused",
        "child_of",
        "classmate_of",
        "colleague_of",
        "emotional",
        "experienced",
        "felt",
        "family",
        "generalizes",
        "guided_by",
        "guide_of",
        "guarded_by",
        "has_member",
        "has_part",
        "has_subtype",
        "has_condition",
        "implies",
        "involves",
        "influences",
        "is",
        "kin_of",
        "knows",
        "knows_boundary",
        "located_in",
        "likes",
        "dislikes",
        "lives_in",
        "member_of",
        "mentor_of",
        "mentored_by",
        "near",
        "neighbor_of",
        "owner_of",
        "owned_by",
        "parent_of",
        "part_of",
        "prefers",
        "preferred_name",
        "participates_in",
        "related_to",
        "sibling_of",
        "student_of",
        "studies_at",
        "teacher_of",
        "uses",
        "visits",
        "witnessed",
        "works_at",
        "helped",
        "relationship",
        "references",
        "subtype_of",
        "supports",
        "specializes",
        "temporal",
        "used_in",
        "guardian_of",
        "owns",
        "friend_of",
    }
)


@dataclass(frozen=True)
class RelationSpec:
    """Semantic direction and salience policy for one relation predicate."""

    predicate: str
    label: str
    symmetric: bool = False
    inverse: Optional[str] = None
    type_prior: float = 0.5


RELATION_REGISTRY: Final[Mapping[str, RelationSpec]] = {
    "parent_of": RelationSpec("parent_of", "父母", inverse="child_of", type_prior=0.95),
    "child_of": RelationSpec("child_of", "子女", inverse="parent_of", type_prior=0.95),
    "sibling_of": RelationSpec(
        "sibling_of", "兄弟姐妹", symmetric=True, type_prior=0.82
    ),
    "kin_of": RelationSpec("kin_of", "家人", symmetric=True, type_prior=0.78),
    "friend_of": RelationSpec("friend_of", "朋友", symmetric=True, type_prior=0.82),
    "classmate_of": RelationSpec(
        "classmate_of", "同学", symmetric=True, type_prior=0.58
    ),
    "colleague_of": RelationSpec(
        "colleague_of", "同事", symmetric=True, type_prior=0.52
    ),
    "neighbor_of": RelationSpec("neighbor_of", "邻居", symmetric=True, type_prior=0.35),
    "acquaintance_of": RelationSpec(
        "acquaintance_of", "认识", symmetric=True, type_prior=0.28
    ),
    "owner_of": RelationSpec("owner_of", "主人", inverse="owned_by", type_prior=0.92),
    "owned_by": RelationSpec("owned_by", "归属于", inverse="owner_of", type_prior=0.92),
    "guardian_of": RelationSpec(
        "guardian_of", "监护", inverse="guarded_by", type_prior=0.88
    ),
    "guarded_by": RelationSpec(
        "guarded_by", "受监护", inverse="guardian_of", type_prior=0.88
    ),
    "mentor_of": RelationSpec(
        "mentor_of", "指导", inverse="mentored_by", type_prior=0.72
    ),
    "mentored_by": RelationSpec(
        "mentored_by", "受指导", inverse="mentor_of", type_prior=0.72
    ),
    "teacher_of": RelationSpec(
        "teacher_of", "教学", inverse="student_of", type_prior=0.68
    ),
    "student_of": RelationSpec(
        "student_of", "学生", inverse="teacher_of", type_prior=0.68
    ),
    "member_of": RelationSpec(
        "member_of", "成员", inverse="has_member", type_prior=0.55
    ),
    "has_member": RelationSpec(
        "has_member", "拥有成员", inverse="member_of", type_prior=0.55
    ),
    "participates_in": RelationSpec("participates_in", "参与", type_prior=0.55),
    "witnessed": RelationSpec("witnessed", "见证", type_prior=0.45),
    "caused": RelationSpec("caused", "导致", inverse="caused_by", type_prior=0.7),
    "caused_by": RelationSpec(
        "caused_by", "由其导致", inverse="caused", type_prior=0.7
    ),
    "helped": RelationSpec("helped", "帮助", type_prior=0.62),
    "guided_by": RelationSpec(
        "guided_by", "由其引导", inverse="guide_of", type_prior=0.62
    ),
    "guide_of": RelationSpec("guide_of", "引导", inverse="guided_by", type_prior=0.62),
    "located_in": RelationSpec("located_in", "位于", type_prior=0.55),
    "lives_in": RelationSpec("lives_in", "居住于", type_prior=0.65),
    "visits": RelationSpec("visits", "访问", type_prior=0.38),
    "works_at": RelationSpec("works_at", "工作于", type_prior=0.48),
    "studies_at": RelationSpec("studies_at", "学习于", type_prior=0.48),
    "near": RelationSpec("near", "靠近", symmetric=True, type_prior=0.32),
    "uses": RelationSpec("uses", "使用", type_prior=0.4),
    "owns": RelationSpec("owns", "拥有", inverse="owned_by", type_prior=0.62),
    "about": RelationSpec("about", "关于", type_prior=0.5),
    "part_of": RelationSpec("part_of", "属于", inverse="has_part", type_prior=0.5),
    "has_part": RelationSpec("has_part", "包含部分", inverse="part_of", type_prior=0.5),
    "subtype_of": RelationSpec(
        "subtype_of", "是其子类", inverse="has_subtype", type_prior=0.5
    ),
    "has_subtype": RelationSpec(
        "has_subtype", "拥有子类", inverse="subtype_of", type_prior=0.5
    ),
    "generalizes": RelationSpec(
        "generalizes", "概括", inverse="specializes", type_prior=0.5
    ),
    "specializes": RelationSpec(
        "specializes", "具体化", inverse="generalizes", type_prior=0.5
    ),
    "implies": RelationSpec("implies", "蕴含", type_prior=0.5),
    "related_to": RelationSpec("related_to", "相关", symmetric=True, type_prior=0.3),
}

ALIASES: Final[Mapping[str, str]] = {
    "causal": "causes",
    "cause": "causes",
    "dislike": "dislikes",
    "favorite": "prefers",
    "involved_in": "involves",
    "like": "likes",
    "relates_to": "related_to",
    # v1 relation spellings are accepted at the boundary and normalized on
    # write. Existing rows remain readable until the development database is
    # rebuilt under v2.
    "family": "kin_of",
    "kin": "kin_of",
    "friend": "friend_of",
    "acquaintance": "acquaintance_of",
    "owner": "owned_by",
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


def relation_spec(predicate: str) -> RelationSpec | None:
    """Return the registered relation semantics for a canonical predicate."""

    try:
        canonical = resolve_predicate(predicate)
    except UnknownPredicateError:
        return None
    return RELATION_REGISTRY.get(canonical)


def relation_importance(predicate: str, supplied: float | None = None) -> float:
    """Use a registry prior while preserving a sourced explicit salience."""

    spec = relation_spec(predicate)
    if supplied is None:
        return spec.type_prior if spec is not None else 0.5
    return min(1.0, max(0.0, float(supplied)))


def relation_context(
    source: str,
    *,
    symmetric: bool,
    specificity: str | None = None,
    role: str | None = None,
) -> str:
    """Encode bounded relation display metadata in the existing context field."""

    fields = [
        "relation",
        source,
        f"symmetry={'symmetric' if symmetric else 'directed'}",
    ]
    if specificity:
        fields.append(f"specificity={specificity}")
    if role:
        fields.append(f"role={role}")
    return "|".join(fields)


__all__ = [
    "ALIASES",
    "PREDICATE_REGISTRY_VERSION",
    "PREDICATES",
    "NON_SEMANTIC_LEGACY_PREDICATES",
    "RELATION_REGISTRY",
    "RelationSpec",
    "UnknownPredicateError",
    "relation_context",
    "relation_importance",
    "relation_spec",
    "resolve_predicate",
]
