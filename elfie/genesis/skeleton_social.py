"""Assemble sourced cohorts and bounded in-law branches above frozen family draws."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from .family import FamilyGenerator, _sample_conditioned_death_age
from .names import allocate_person_names
from .skeleton import SkeletonGroup, SkeletonPerson, SkeletonRelationship
from .skeleton_graph import FAMILY_ROLES

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext
    from .contracts import RelationshipSeed


def expand_partner_siblings(
    compiler: GenesisCompiler, request: GenesisCompileInput, context: LifeContext
) -> LifeContext:
    graph = context.family_graph
    assert graph is not None
    if graph.partner_origin is None:
        return context
    genesis = compiler._species(request.species_id).genesis
    assert genesis is not None
    generator = FamilyGenerator(
        species_id=request.species_id,
        genesis=genesis,
        policy=compiler._source.generation_policy,
        seed_for=lambda label: compiler._domain_seed(request.appearance_seed, label),
    )
    branches = []
    for sibling in graph.partner_origin.group.children:
        if sibling.person_id == graph.partner_origin.anchor.person_id:
            continue
        branch = generator._generate_descendant_family(
            sibling,
            union_id=f"{sibling.person_id}:own",
            partner_id=f"{sibling.person_id}:partner",
            child_id_prefix=f"{sibling.person_id}:child",
        )
        if branch is not None:
            branches.append(branch)
    return replace(context, partner_sibling_families=tuple(branches))


def enrich_social_graph(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    context: LifeContext,
    proposals: tuple[RelationshipSeed, ...],
) -> tuple[LifeContext, tuple[RelationshipSeed, ...]]:
    from .compiler import stage_for_age

    people = {p.person_id: p for p in context.people}
    edges = list(context.relationships)
    slots = list(context.activities)
    groups = []
    graph = context.family_graph
    assert graph is not None
    families = [graph.core.origin]
    if graph.core.own:
        families.append(graph.core.own)
    families.extend(b.group for b in graph.ancestor_families)
    families.extend(b.group for b in graph.sibling_families)
    families.extend(b.group for b in graph.child_families)
    families.extend(b.group for b in graph.aunt_uncle_families)
    families.extend(b.group for b in context.partner_sibling_families)
    if graph.partner_origin:
        families.append(graph.partner_origin.group)
    for family in families:
        union = family.union
        nuclear_members = (
            union.first.person_id,
            union.second.person_id,
            *(c.person_id for c in family.children),
        )
        groups.append(
            SkeletonGroup(
                f"group:family:{union.union_id}",
                "family",
                "夫妻与子女家庭",
                nuclear_members,
                f"family:{union.union_id}",
            )
        )
        for index, child in enumerate(family.children):
            for other in family.children[index + 1 :]:
                edges.append(
                    SkeletonRelationship(
                        child.person_id,
                        other.person_id,
                        "sibling",
                        "established",
                        f"family:{union.union_id}",
                    )
                )

    # Branch groups reference shared people; they never create another copy.
    roots = [(graph.core.origin, "自己的父母及后代")]
    roots.extend((b.group, "祖辈及后代") for b in graph.ancestor_families)
    if graph.partner_origin:
        roots.append((graph.partner_origin.group, "配偶的父母及后代"))
    for family, label in roots:
        members = {family.union.first.person_id, family.union.second.person_id}
        pending = list(members)
        while pending:
            parent = pending.pop()
            adjacent = {
                e.object_id
                for e in edges
                if e.subject_id == parent and e.relation in {"parent_of", "partner"}
            }
            adjacent.update(
                e.subject_id
                for e in edges
                if e.object_id == parent and e.relation == "partner"
            )
            for linked_id in adjacent - members:
                members.add(linked_id)
                pending.append(linked_id)
        groups.append(
            SkeletonGroup(
                f"group:branch:{family.union.union_id}",
                "family",
                label,
                tuple(sorted(members)),
                f"family:{family.union.union_id}",
            )
        )

    # A cohort is tied to an actual shared interval; a work colleague is not
    # inferred merely because that person previously acted as the teacher.
    segments = []
    for segment in context.life_segments:
        if (
            segment.kind not in {"learning", "work"}
            or segment.end_age_year <= segment.start_age_year
        ):
            segments.append(segment)
            continue
        cohort_relation = "classmate" if segment.kind == "learning" else "colleague"
        rng = random.Random(
            compiler._domain_seed(
                request.appearance_seed, f"learning:cohort:{segment.segment_id}"
            )
        )
        distribution = compiler._source.generation_policy.cohort_count_distribution
        count = rng.choices(
            [n for n, _ in distribution], weights=[w for _, w in distribution]
        )[0]
        participants = (
            list(segment.participant_ids) if segment.kind == "learning" else []
        )
        for index in range(count):
            ident = f"contact:{segment.kind}:peer:{index}"
            people[ident] = SkeletonPerson(
                ident,
                ident,
                request.species_id,
                rng.choice(("male", "female")),
                0,
                segment.segment_id,
            )
            participants.append(ident)
            edges.append(
                SkeletonRelationship(
                    "self", ident, cohort_relation, "contact_slot", segment.segment_id
                )
            )
        participant_ids = tuple(participants)
        segments.append(replace(segment, participant_ids=participant_ids))
        slots = [
            replace(a, participant_ids=participant_ids)
            if segment.segment_id in a.depends_on and a.purpose == segment.kind
            else a
            for a in slots
        ]
        groups.append(
            SkeletonGroup(
                f"group:{segment.segment_id}",
                segment.kind,
                "师徒学习同伴" if segment.kind == "learning" else "共同工作同伴",
                ("self", *participant_ids),
                segment.segment_id,
            )
        )
        if segment.kind == "learning":
            teacher = segment.participant_ids[0]
            for peer in participant_ids:
                if peer != teacher:
                    edges.append(
                        SkeletonRelationship(
                            peer, teacher, "teacher", "contact_slot", segment.segment_id
                        )
                    )
        for first, second in zip(participant_ids, participant_ids[1:]):
            edges.append(
                SkeletonRelationship(
                    first,
                    second,
                    "acquaintance"
                    if segment.kind == "learning"
                    and first == segment.participant_ids[0]
                    else cohort_relation,
                    "contact_slot",
                    segment.segment_id,
                )
            )

    # Existing growth contacts share one gathering only when they are known
    # and alive then. The shared slot is evidence for their mutual contact.
    growth = [a for a in slots if a.direction == "growth" and a.status != "excluded"]
    if growth:
        gathering = max(growth, key=lambda a: (a.age_year, a.start_day))
        records = {r.person_id: r for r in proposals}
        growth_members = []
        for activity in growth:
            for ident in activity.participant_ids:
                birth = people[ident].birth_age_year
                death = records[ident].death_event_age_years
                if (
                    birth is not None
                    and birth <= gathering.age_year
                    and (death is None or death > gathering.age_year)
                    and ident not in growth_members
                ):
                    growth_members.append(ident)
        members_tuple = tuple(growth_members)
        slots = [
            replace(a, participant_ids=members_tuple)
            if a.activity_id == gathering.activity_id
            else a
            for a in slots
        ]
        groups.append(
            SkeletonGroup(
                "group:growth:home",
                "growth",
                "共同生活的邻里伙伴",
                ("self", *members_tuple),
                gathering.activity_id,
            )
        )
        for first, second in zip(members_tuple, members_tuple[1:]):
            edges.append(
                SkeletonRelationship(
                    first, second, "acquaintance", "contact_slot", gathering.activity_id
                )
            )
    for slot in slots:
        if slot.direction != "public" or slot.status == "excluded":
            continue
        groups.append(
            SkeletonGroup(
                f"group:{slot.activity_id}",
                "public",
                slot.purpose,
                ("self", *slot.participant_ids),
                slot.activity_id,
            )
        )
        for first, second in zip(slot.participant_ids, slot.participant_ids[1:]):
            edges.append(
                SkeletonRelationship(
                    first, second, "acquaintance", "contact_slot", slot.activity_id
                )
            )

    # Travel may reuse known companions; a visit alone is still a valid visit.
    for index, slot in enumerate(slots):
        if slot.direction != "travel" or slot.status == "excluded":
            continue
        eligible = []
        for record in proposals:
            if (
                record.role not in {"friend", "neighbor"}
                or record.relationship_start_age is None
                or record.relationship_start_age > slot.age_year
            ):
                continue
            person = people[record.person_id]
            birth = person.birth_age_year
            if birth is None or (
                person.death_age_year is not None
                and person.death_age_year <= slot.age_year
            ):
                continue
            species_id = {"Saevi": "saevi", "Tovren": "tovren", "Myelle": "myelle"}.get(
                person.species_id, person.species_id
            )
            genesis = compiler._species(species_id).genesis
            assert genesis is not None
            if 0 <= slot.age_year - birth < genesis.terminal_age_years:
                eligible.append(record.person_id)
        rng = random.Random(
            compiler._domain_seed(
                request.appearance_seed,
                f"episodes:travel-companions:{slot.activity_id}",
            )
        )
        distribution = compiler._source.generation_policy.cohort_count_distribution
        count = min(
            len(eligible),
            rng.choices(
                [n for n, _ in distribution], weights=[w for _, w in distribution]
            )[0],
        )
        companion_ids = tuple(rng.sample(eligible, count))
        if companion_ids:
            slots[index] = replace(
                slot,
                participant_ids=tuple(
                    dict.fromkeys((*slot.participant_ids, *companion_ids))
                ),
            )
            groups.append(
                SkeletonGroup(
                    f"group:{slot.activity_id}",
                    "travel",
                    "旅游探索同行者",
                    ("self", *slots[index].participant_ids),
                    slot.activity_id,
                )
            )
            for first, second in zip(companion_ids, companion_ids[1:]):
                edges.append(
                    SkeletonRelationship(
                        first, second, "acquaintance", "contact_slot", slot.activity_id
                    )
                )

    reserved = [
        p.display_name
        for p in people.values()
        if p.person_id == "self"
        or p.person_id in {r.person_id for r in proposals if r.object_kind != "elfie"}
    ]
    allocated = allocate_person_names(
        compiler._source,
        request.appearance_seed,
        (
            (p.person_id, p.species_id)
            for p in people.values()
            if p.person_id != "self"
            and p.person_id
            not in {r.person_id for r in proposals if r.object_kind != "elfie"}
        ),
        reserved,
        seed_for=compiler._domain_seed,
    )
    for ident, person in people.items():
        gender = person.gender
        if gender == "unknown" and ident in allocated:
            gender = random.Random(
                compiler._domain_seed(
                    request.appearance_seed, f"learning:gender:{ident}"
                )
            ).choice(("male", "female"))
        people[ident] = replace(
            person,
            species_id={"Saevi": "saevi", "Tovren": "tovren", "Myelle": "myelle"}.get(
                person.species_id, person.species_id
            ),
            display_name=allocated.get(ident, person.display_name),
            gender=gender,
        )
    proposed_ids = {
        r.person_id
        for r in proposals
        if r.role in FAMILY_ROLES
        or r.object_kind != "elfie"
        or r.life_status == "deceased"
    }
    for ident, person in people.items():
        if ident == "self" or ident in proposed_ids or person.birth_age_year is None:
            continue
        genesis = compiler._species(person.species_id).genesis
        assert genesis is not None
        last_contact = max(
            (
                a.age_year
                for a in slots
                if a.status != "excluded" and ident in a.participant_ids
            ),
            default=0,
        )
        death_age = _sample_conditioned_death_age(
            elder_start_age=genesis.stage_ranges["elder"][0],
            median_age=genesis.median_age_years,
            terminal_age=genesis.terminal_age_years,
            minimum_survival_age=max(0, last_contact - person.birth_age_year),
            early_cdf_power=compiler._source.generation_policy.family.lifespan.early_cdf_power,
            late_survival_power=compiler._source.generation_policy.family.lifespan.late_survival_power,
            uniform=compiler._domain_uniform(
                request.appearance_seed, f"episodes:social-lifespan:{ident}"
            ),
        )
        death_year = person.birth_age_year + death_age
        if death_year <= context.identity.age_years_at_adoption:
            people[ident] = replace(person, death_age_year=death_year)
    normalized = []
    for relation in proposals:
        person = people[relation.person_id]
        person_age = relation.age_years_at_genesis
        deceased = (
            person.death_age_year is not None and relation.role not in FAMILY_ROLES
        )
        if deceased:
            person_age = None
        normalized.append(
            replace(
                relation,
                display_name=person.display_name,
                age_years_at_genesis=person_age,
                life_status="deceased" if deceased else relation.life_status,
                death_event_age_years=person.death_age_year
                if deceased
                else relation.death_event_age_years,
                death_age_years_at_genesis=(
                    person.death_age_year - person.birth_age_year
                    if deceased
                    and person.death_age_year is not None
                    and person.birth_age_year is not None
                    else relation.death_age_years_at_genesis
                ),
                person_species_id=person.species_id
                if relation.object_kind == "elfie"
                else relation.person_species_id,
                related_species_id=person.species_id
                if relation.object_kind == "elfie"
                else relation.related_species_id,
                person_gender=person.gender
                if relation.object_kind == "elfie"
                else relation.person_gender,
                age_band_at_genesis=stage_for_age(
                    person.species_id, person_age, compiler._catalog
                )
                if person_age is not None and relation.object_kind == "elfie"
                else ""
                if deceased
                else relation.age_band_at_genesis,
                aliases=tuple(
                    person.display_name if a == relation.display_name else a
                    for a in relation.aliases
                ),
            )
        )
    # A primary main-person role and its structural equivalent share one edge.
    distinct = {}
    for edge in edges:
        key = (edge.subject_id, edge.relation, edge.object_id)
        if key not in distinct or edge.source_ref.startswith("family:"):
            distinct[key] = edge
    return replace(
        context,
        people=tuple(people.values()),
        relationships=tuple(distinct.values()),
        groups=tuple(g for g in groups if len(set(g.member_ids)) >= 3),
        life_segments=tuple(segments),
        activities=tuple(slots),
    ), tuple(normalized)
