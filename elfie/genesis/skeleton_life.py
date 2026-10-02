"""Build fixed life intervals before assigning discretionary activities."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from .skeleton import (
    LifeSegment,
    PersonalPlaceLink,
    SkeletonDecision,
    SkeletonKnowledge,
    SkeletonPerson,
    SkeletonPlace,
    SkeletonRelationship,
)
from .skeleton_graph import build_graph_indices, fresh_contact_name
from .world import WorldPlaceRelation

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext
    from .contracts import RelationshipSeed


def build_life_skeleton(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    context: LifeContext,
    relationships: tuple[RelationshipSeed, ...],
) -> LifeContext:
    source = compiler._source
    age = context.identity.age_years_at_adoption
    home = context.origin.childhood_home_place_id
    public_home = context.origin.predeparture_home_place_id
    days = source.geography_network.days_per_local_year
    people, edges, places, public_edges = build_graph_indices(
        compiler, request, context, relationships
    )
    segments = [
        LifeSegment(
            "residence:home", "residence", 0, age, home, (), 0, "birth:residence"
        )
    ]
    caregivers = tuple(
        r.person_id for r in relationships if "self" in r.care_recipient_person_ids
    )
    if caregivers:
        childhood_end = compiler._species(request.species_id).genesis.stage_ranges[
            "childhood"
        ][1]
        segments.append(
            LifeSegment(
                "care:childhood",
                "care",
                0,
                min(age, childhood_end),
                home,
                caregivers,
                0,
                "family:care",
            )
        )
    # The existing family care links determine the need; only the time budget
    # is new, not any family member or relation.
    policy = source.learning_policy
    for child in relationships:
        if child.role != "child" or "self" not in child.caregiver_person_ids:
            continue
        birth = next(p.birth_age_year for p in people if p.person_id == child.person_id)
        if birth is None or birth > age:
            continue
        care_end = min(
            age,
            birth
            + compiler._species(request.species_id).genesis.stage_ranges["childhood"][
                1
            ],
        )
        segments.append(
            LifeSegment(
                f"care:{child.person_id}",
                "care",
                max(0, birth),
                care_end,
                home,
                (child.person_id,),
                policy.care_days_per_year,
                "family:child-care",
            )
        )
    links = [
        PersonalPlaceLink(home, "residence", 0, age, "established", "residence:home")
    ]
    decisions = [
        SkeletonDecision(
            "residence:home",
            "growth",
            "established",
            "无已确定迁居原因，保留连续住所，不虚构迁移",
            "birth:residence",
        )
    ]
    learning = context.learning
    policy = source.learning_policy
    if policy.vocations and age >= policy.minimum_start_age_years:
        rng = random.Random(
            compiler._domain_seed(request.appearance_seed, "learning:vocation")
        )
        vocation = policy.vocations[rng.randrange(len(policy.vocations))]
        start = policy.minimum_start_age_years
        mature_start, mature_end = compiler._species(
            request.species_id
        ).genesis.stage_ranges["mature"]
        finish = start + vocation.apprenticeship_years
        teacher_id = f"contact:teacher:{vocation.vocation_id}"
        teacher_name = fresh_contact_name(compiler, request, people)
        people.append(
            SkeletonPerson(
                teacher_id,
                teacher_name,
                request.species_id,
                "unknown",
                start - mature_start,
                "learning:teacher",
            )
        )
        edges.append(
            SkeletonRelationship(
                "self", teacher_id, "teacher", "contact_slot", "learning:teacher"
            )
        )
        workspace = f"private:{request.elfie_id}:practice"
        places.append(
            SkeletonPlace(
                workspace,
                f"{vocation.label}的师徒实践地点",
                public_home,
                "learning:local-practice",
            )
        )
        public_edges.append(
            WorldPlaceRelation(
                workspace, "located_in", public_home, "learning:local-practice"
            )
        )
        segments.append(
            LifeSegment(
                "learning:apprenticeship",
                "learning",
                start,
                min(age, finish),
                workspace,
                (teacher_id,),
                policy.learning_days_per_year,
                "rules.learning",
                vocation.vocation_id,
                vocation.apprenticeship_years,
            )
        )
        links.append(
            PersonalPlaceLink(
                workspace,
                "learning",
                start,
                min(age, finish),
                "planned",
                "learning:apprenticeship",
            )
        )
        learning = replace(
            learning,
            path_id="apprenticeship",
            institution_ids=(workspace,),
            apprenticeship_ids=("learning:apprenticeship",),
        )
        work_start = max(finish, mature_start)
        if age > work_start:
            segments.append(
                LifeSegment(
                    "work:practice",
                    "work",
                    work_start,
                    min(age, mature_end),
                    workspace,
                    (teacher_id,),
                    policy.work_days_per_year,
                    "rules.learning",
                    vocation.vocation_id,
                    vocation.apprenticeship_years,
                )
            )
            links.append(
                PersonalPlaceLink(
                    workspace,
                    "work",
                    work_start,
                    min(age, mature_end),
                    "planned",
                    "work:practice",
                )
            )
    else:
        decisions.append(
            SkeletonDecision(
                "learning",
                "learning_work",
                "not_applicable",
                "未适龄或资料包没有可用师徒职业配置",
                "rules.learning",
            )
        )
    knowledge = tuple(
        SkeletonKnowledge(
            f.fact_id,
            f.prerequisite_ids,
            f.related_ids,
            f.source_ref,
            tuple((c.kind, c.attributes) for c in f.conditions),
            f.graph_nodes,
            f.graph_assertions,
        )
        for f in source.knowledge
    )
    return replace(
        context,
        people=tuple(people),
        places=tuple(sorted(places, key=lambda p: p.place_id)),
        routes=source.routes,
        place_relations=tuple(public_edges),
        relationships=tuple(edges),
        life_segments=tuple(segments),
        place_links=tuple(links),
        knowledge_nodes=knowledge,
        decisions=tuple(decisions),
        days_per_year=days,
        learning=learning,
        content_hash="",
    )
