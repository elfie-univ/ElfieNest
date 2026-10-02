"""Project preserved family and shared geography into skeleton indices."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .skeleton import SkeletonPerson, SkeletonPlace, SkeletonRelationship
from .world import WorldPlaceRelation

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext
    from .contracts import RelationshipSeed

FAMILY_ROLES = frozenset(
    (
        "parent",
        "sibling",
        "partner",
        "child",
        "partner_parent",
        "partner_sibling",
        "grandparent",
        "aunt_uncle",
        "sibling_partner",
        "child_partner",
        "aunt_uncle_partner",
        "niece_nephew",
        "grandchild",
        "cousin",
        "partner_sibling_partner",
        "partner_niece_nephew",
    )
)


def fresh_contact_name(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    people: list[SkeletonPerson],
) -> str:
    existing = {person.display_name for person in people}
    names = compiler._generated_names_for_species(
        request, request.species_id, len(people) + 1
    )
    return next(name for name in names if name not in existing)


def build_graph_indices(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    context: LifeContext,
    relationships: tuple[RelationshipSeed, ...],
) -> tuple[
    list[SkeletonPerson],
    list[SkeletonRelationship],
    list[SkeletonPlace],
    list[WorldPlaceRelation],
]:
    source = compiler._source
    age = context.identity.age_years_at_adoption
    home = context.origin.childhood_home_place_id
    public_home = context.origin.predeparture_home_place_id
    people = [
        SkeletonPerson(
            "self",
            context.identity.original_name,
            request.species_id,
            request.gender,
            0,
            "accepted-identity",
        )
    ]
    edges = []
    for relation in relationships:
        person_age = relation.age_years_at_genesis
        # Preserve unknown birth times of deceased social contacts.
        birth = age - person_age if person_age is not None else None
        people.append(
            SkeletonPerson(
                relation.person_id,
                relation.display_name,
                relation.person_species_id,
                relation.person_gender or "unknown",
                birth,
                relation.source_ref,
                death_age_year=relation.death_event_age_years,
            )
        )
        edges.append(
            SkeletonRelationship(
                "self",
                relation.person_id,
                relation.role,
                "established" if relation.role in FAMILY_ROLES else "contact_slot",
                relation.source_ref,
            )
        )
    graph = context.family_graph
    assert graph is not None
    groups = [graph.core.origin]
    if graph.core.own is not None:
        groups.append(graph.core.own)
    groups.extend(b.group for b in graph.ancestor_families)
    groups.extend(b.group for b in graph.sibling_families)
    groups.extend(b.group for b in graph.child_families)
    groups.extend(b.group for b in graph.aunt_uncle_families)
    if graph.partner_origin is not None:
        groups.append(graph.partner_origin.group)
    groups.extend(b.group for b in context.partner_sibling_families)
    births = {}
    for group in groups:
        union = group.union
        for person in (union.first, union.second, *group.children):
            births[person.person_id] = age + person.birth_year
        edges.append(
            SkeletonRelationship(
                union.first.person_id,
                union.second.person_id,
                "partner",
                "established",
                f"family:{union.union_id}",
            )
        )
        for child in group.children:
            for parent in (union.first, union.second):
                edges.append(
                    SkeletonRelationship(
                        parent.person_id,
                        child.person_id,
                        "parent_of",
                        "established",
                        f"family:{union.union_id}",
                    )
                )
    people = [
        replace(p, birth_age_year=births.get(p.person_id, p.birth_age_year))
        for p in people
    ]
    places = [
        SkeletonPlace(p.place_id, p.label, p.parent_id, f"world:{p.place_id}")
        for p in source.places
    ]
    ids = {p.place_id for p in places}
    public_edges = list(source.place_relations)
    for ident in (
        {source.world_id, source.known_region_id}
        | {x for e in public_edges for x in (e.subject_id, e.object_id)}
        | {p.parent_id for p in places if p.parent_id}
    ):
        if ident not in ids:
            places.append(SkeletonPlace(ident, ident, "", "world:hierarchy"))
            ids.add(ident)
    places.append(SkeletonPlace(home, "我的住所", public_home, "birth:private-home"))
    public_edges.append(
        WorldPlaceRelation(home, "located_in", public_home, "birth:private-home")
    )
    return people, edges, places, public_edges
