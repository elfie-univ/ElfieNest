"""One bounded family expansion for the most important established friends."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .contracts import RelationshipSeed
from .family import CoreFamily, FamilyGenerator, FamilyGroup, FamilyPerson
from .names import allocate_person_names
from .skeleton import SkeletonGroup, SkeletonPerson, SkeletonRelationship

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext


def expand_important_friend_families(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    context: LifeContext,
    proposals: tuple[RelationshipSeed, ...],
) -> tuple[LifeContext, tuple[RelationshipSeed, ...]]:
    from .compiler import stage_for_age

    people = {p.person_id: p for p in context.people}
    edges = list(context.relationships)
    groups = list(context.groups)
    records = list(proposals)
    cores = []
    candidates = sorted(
        (
            r
            for r in proposals
            if r.role == "friend"
            and r.life_status == "alive"
            and r.object_kind == "elfie"
            and people[r.person_id].birth_age_year is not None
        ),
        key=lambda r: (-r.importance, r.person_id),
    )[: min(2, compiler._source.generation_policy.friend_max_count)]
    current_age = context.identity.age_years_at_adoption
    for friend in candidates:
        anchor = people[friend.person_id]
        genesis = compiler._species(anchor.species_id).genesis
        assert genesis is not None and anchor.birth_age_year is not None
        generator = FamilyGenerator(
            species_id=anchor.species_id,
            genesis=genesis,
            policy=compiler._source.generation_policy,
            seed_for=lambda label, ident=anchor.person_id: compiler._domain_seed(
                request.appearance_seed,
                f"episodes:important-friend-family:{ident}:{label}",
            ),
        )
        raw = generator.generate_core_family(
            FamilyPerson(
                anchor.person_id,
                anchor.species_id,
                anchor.gender,
                anchor.birth_age_year - current_age,
            )
        )
        prefix = f"important-friend:{anchor.person_id}:"

        def person(
            p: FamilyPerson, anchor_id: str = anchor.person_id, namespace: str = prefix
        ) -> FamilyPerson:
            return replace(
                p,
                person_id=p.person_id
                if p.person_id == anchor_id
                else namespace + p.person_id,
            )

        def family(g: FamilyGroup, namespace: str = prefix) -> FamilyGroup:
            return replace(
                g,
                union=replace(
                    g.union,
                    union_id=namespace + g.union.union_id,
                    first=person(g.union.first),
                    second=person(g.union.second),
                ),
                children=tuple(person(c) for c in g.children),
            )

        core = CoreFamily(
            person(raw.protagonist),
            family(raw.origin),
            family(raw.own) if raw.own else None,
        )
        cores.append(core)
        members = {}
        for g in (core.origin, core.own):
            if g is None:
                continue
            source = f"family:{g.union.union_id}"
            parents = (g.union.first, g.union.second)
            ids = tuple(p.person_id for p in (*parents, *g.children))
            if len(set(ids)) >= 3:
                groups.append(
                    SkeletonGroup(
                        f"group:{source}",
                        "family",
                        f"重要朋友{anchor.display_name}的家庭",
                        ids,
                        source,
                    )
                )
            edges.append(
                SkeletonRelationship(
                    parents[0].person_id,
                    parents[1].person_id,
                    "partner",
                    "established",
                    source,
                )
            )
            for p in parents:
                for c in g.children:
                    edges.append(
                        SkeletonRelationship(
                            p.person_id, c.person_id, "parent_of", "established", source
                        )
                    )
            for p in (*parents, *g.children):
                if p.person_id != anchor.person_id:
                    members[p.person_id] = p
        for ident, p in members.items():
            is_parent = ident in {
                core.origin.union.first.person_id,
                core.origin.union.second.person_id,
            }
            role = (
                ("父亲" if p.gender == "male" else "母亲") if is_parent else "兄弟姐妹"
            )
            if not is_parent:
                older = p.birth_year < core.protagonist.birth_year
                same_year = p.birth_year == core.protagonist.birth_year
                role = (
                    ("兄弟" if same_year else "哥哥" if older else "弟弟")
                    if p.gender == "male"
                    else ("姐妹" if same_year else "姐姐" if older else "妹妹")
                )
            if core.own:
                if ident in {
                    core.own.union.first.person_id,
                    core.own.union.second.person_id,
                }:
                    role = "配偶"
                elif ident in {c.person_id for c in core.own.children}:
                    role = "儿子" if p.gender == "male" else "女儿"
            label = f"朋友{anchor.display_name}的{role}"
            source = f"important-friend-family:{anchor.person_id}"
            edges.append(
                SkeletonRelationship(
                    "self",
                    ident,
                    "friend_family",
                    "established",
                    source,
                    label,
                    ("self", anchor.person_id, ident),
                )
            )
            birth = p.birth_year + current_age
            deceased = p.death_year is not None and p.death_year <= 0
            death = p.death_year + current_age if deceased else None
            people[ident] = SkeletonPerson(
                ident,
                label,
                p.species_id,
                p.gender,
                birth,
                source,
                death_age_year=death,
            )
            age = None if deceased else -p.birth_year
            records.append(
                RelationshipSeed(
                    person_id=ident,
                    display_name=label,
                    role="friend_family",
                    initial_trust=0.5,
                    shared_facts=(
                        f"{label}；家庭关系由朋友处获知，尚无实际接触记录。",
                    ),
                    unknown_facts=("对方未分享的生活与个人性格。",),
                    relationship_id=f"rel:{ident}",
                    subject_id=f"elfie:{request.elfie_id}",
                    object_id=ident,
                    object_kind="elfie",
                    direction="elfie_to_elfie",
                    familiarity="heard",
                    importance=min(0.4, friend.importance),
                    aliases=(label,),
                    retrieval_terms=("朋友的家人", anchor.person_id),
                    source="important_friend_family",
                    source_ref=source,
                    person_species_id=p.species_id,
                    related_species_id=p.species_id,
                    person_gender=p.gender,
                    age_years_at_genesis=age,
                    age_band_at_genesis=stage_for_age(
                        p.species_id, age, compiler._catalog
                    )
                    if age is not None
                    else "",
                    life_status="deceased" if deceased else "alive",
                    death_age_years_at_genesis=p.death_year - p.birth_year
                    if deceased
                    else None,
                    related_person_ids=(anchor.person_id,),
                )
            )
    new_ids = {r.person_id for r in records if r.source == "important_friend_family"}
    names = allocate_person_names(
        compiler._source,
        request.appearance_seed,
        ((ident, people[ident].species_id) for ident in sorted(new_ids)),
        (p.display_name for ident, p in people.items() if ident not in new_ids),
        seed_for=compiler._domain_seed,
    )
    for ident in new_ids:
        people[ident] = replace(people[ident], display_name=names[ident])
    records = [
        replace(
            r, display_name=names[r.person_id], aliases=(names[r.person_id], *r.aliases)
        )
        if r.person_id in names
        else r
        for r in records
    ]
    return replace(
        context,
        people=tuple(people.values()),
        relationships=tuple(edges),
        groups=tuple(groups),
        important_friend_families=tuple(cores),
    ), tuple(records)
