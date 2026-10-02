"""Stage four: resolve ordered slots before admitting contact/visit facts."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .contracts import EpisodeSeed, RelationshipSeed
from .skeleton_graph import FAMILY_ROLES

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext


def materialize_skeleton(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    skeleton: LifeContext,
    proposals: tuple[RelationshipSeed, ...],
) -> tuple[LifeContext, tuple[RelationshipSeed, ...], tuple[EpisodeSeed, ...]]:
    from .compiler import _content_hash, stage_for_age

    relationships = {
        r.person_id: r
        for r in proposals
        if r.role in FAMILY_ROLES or r.source == "adoption_decision"
    }
    proposed = {r.person_id: r for r in proposals}
    people = {p.person_id: p for p in skeleton.people}
    completed = []
    episodes = []
    practice_years: dict[str, set[int]] = {}
    qualified: set[str] = set()
    visit_counts: dict[str, int] = {}
    visit_purposes: dict[str, set[str]] = {}
    visit_stays: dict[str, int] = {}
    visit_ages: dict[str, list[int]] = {}
    visit_records: dict[str, tuple[tuple[str, ...], str, int]] = {}
    visit_routes: dict[str, tuple[str, ...]] = {}
    visit_travel: dict[str, int] = {}
    familiar_routes: set[str] = set()
    observed: set[str] = set()
    unmade = {
        (identifier, reason): count
        for identifier, count, reason in skeleton.mobility.unmade_opportunity_records
    }
    for slot in skeleton.activities:
        if slot.status == "excluded":
            if slot.direction == "travel":
                key = (slot.source_ref.removeprefix("visit-opportunity:"), slot.reason)
                unmade[key] = unmade.get(key, 0) + 1
            completed.append(slot)
            continue
        reason = ""
        if "apprenticeship_completed" in slot.prerequisites and not qualified:
            reason = "尚未完成足够年限的实际师徒学习"
        if reason:
            completed.append(replace(slot, status="excluded", reason=reason))
            continue
        completed.append(replace(slot, status="completed"))
        for person_id in slot.participant_ids:
            if person_id in relationships:
                continue
            if person_id in proposed:
                relationships[person_id] = proposed[person_id]
                continue
            person = people[person_id]
            role = next(
                (
                    e.relation
                    for e in skeleton.relationships
                    if e.subject_id == "self" and e.object_id == person_id
                ),
                "activity_contact",
            )
            importance = compiler._source.generation_policy.relationship_importance(
                role, 0.45
            )
            relationships[person_id] = RelationshipSeed(
                person_id=person_id,
                display_name=person.display_name,
                role=role,
                initial_trust=0.5,
                shared_facts=(f"我们在{slot.purpose}中实际接触。",),
                unknown_facts=("对方没有分享的完整生活。",),
                relationship_id=f"rel:{person_id}",
                subject_id=f"elfie:{request.elfie_id}",
                object_id=person_id,
                object_kind="elfie",
                direction="elfie_to_elfie",
                familiarity="acquainted",
                importance=importance,
                aliases=(person.display_name, role),
                retrieval_terms=(role, person_id),
                source_ref=slot.activity_id,
                person_species_id=person.species_id,
                related_species_id=person.species_id,
                person_gender=person.gender,
                relationship_start_age=slot.age_year,
                age_years_at_genesis=(
                    skeleton.identity.age_years_at_adoption - person.birth_age_year
                    if person.birth_age_year is not None
                    and person.death_age_year is None
                    else None
                ),
                life_status="deceased"
                if person.death_age_year is not None
                else "alive",
                death_event_age_years=person.death_age_year,
                death_age_years_at_genesis=(
                    person.death_age_year - person.birth_age_year
                    if person.death_age_year is not None
                    and person.birth_age_year is not None
                    else None
                ),
                home_place_id=person.home_place_id,
                age_band_at_genesis=(
                    stage_for_age(
                        request.species_id,
                        skeleton.identity.age_years_at_adoption - person.birth_age_year,
                        compiler._catalog,
                    )
                    if person.birth_age_year is not None
                    and person.death_age_year is None
                    else ""
                ),
                eligible_episode_theme_ids=(),
            )
        if slot.direction in {"public", "learning_work"}:
            episodes.append(
                EpisodeSeed(
                    seed_id=slot.activity_id,
                    event_kind="learning" if slot.purpose == "learning" else "activity",
                    content=f"我在{slot.age_year}岁这一年的本地第{slot.start_day + 1}日起，参加了{slot.purpose}，持续{slot.stay_days or slot.duration_days}天。",
                    source_ref=slot.activity_id,
                    topic=f"biography.{slot.direction}",
                    aliases=(slot.purpose,),
                    retrieval_terms=(slot.purpose, slot.activity_id),
                    life_stage=stage_for_age(
                        request.species_id, slot.age_year, compiler._catalog
                    ),
                    place_ids=slot.place_ids,
                    person_ids=slot.participant_ids,
                    route_ids=slot.route_ids,
                    result=f"完成{slot.purpose}中的实际参与或实践。",
                    theme_id=slot.direction,
                    feeling="具体感受未记录。",
                    age_years_at_event=slot.age_year,
                    stay_days=slot.stay_days or slot.duration_days,
                    travel_days=slot.travel_days,
                    purposes=(slot.purpose,),
                )
            )
        if slot.purpose == "learning":
            segment = next(
                s for s in skeleton.life_segments if s.segment_id in slot.depends_on
            )
            years = practice_years.setdefault(segment.vocation_id, set())
            years.add(slot.age_year)
            if len(years) >= segment.required_years:
                qualified.add(segment.vocation_id)
                episodes.append(
                    EpisodeSeed(
                        seed_id=f"{slot.activity_id}:completed",
                        event_kind="learning",
                        content="经过规定年限的师徒实践，导师确认了我的基本实践能力。",
                        source_ref=slot.activity_id,
                        topic="biography.learning",
                        place_ids=slot.place_ids,
                        aliases=("学徒结业",),
                        retrieval_terms=("学徒", "实践资格"),
                        person_ids=slot.participant_ids,
                        result="完成学徒训练，具备基本实践资格，尚不代表精通。",
                        feeling="具体感受未记录。",
                        theme_id="apprenticeship-completion",
                        predecessor_ids=(slot.activity_id,),
                        age_years_at_event=slot.age_year,
                        life_stage=stage_for_age(
                            request.species_id, slot.age_year, compiler._catalog
                        ),
                    )
                )
        if slot.direction not in {"travel", "public", "departure"}:
            continue
        if slot.direction == "travel":
            opportunity = slot.source_ref.removeprefix("visit-opportunity:")
            visit_ages.setdefault(opportunity, []).append(slot.age_year)
            visit_records.setdefault(
                opportunity, (slot.place_ids, slot.purpose, slot.stay_days)
            )
            visit_routes[opportunity] = slot.route_ids
            visit_travel[opportunity] = slot.travel_days
        for place in slot.place_ids:
            if place in slot.observed_place_ids:
                observed.add(place)
                continue
            visit_counts[place] = visit_counts.get(place, 0) + 1
            visit_purposes.setdefault(place, set()).add(slot.purpose)
            visit_stays[place] = max(visit_stays.get(place, 0), slot.stay_days)
        familiar_routes.update(slot.route_ids)
    mobility = replace(
        skeleton.mobility,
        visited_place_ids=tuple(sorted(visit_counts)),
        familiar_route_ids=tuple(sorted(familiar_routes)),
        visit_counts=tuple(sorted(visit_counts.items())),
        visit_purposes=tuple(
            (p, ",".join(sorted(v))) for p, v in sorted(visit_purposes.items())
        ),
        visit_stay_days=tuple(sorted(visit_stays.items())),
        visit_age_years=tuple(
            (p, tuple(sorted(v))) for p, v in sorted(visit_ages.items())
        ),
        opportunity_records=tuple(
            (p, v[0], len(visit_ages[p]), v[1], v[2])
            for p, v in sorted(visit_records.items())
        ),
        opportunity_route_ids=tuple(sorted(visit_routes.items())),
        opportunity_travel_days=tuple(sorted(visit_travel.items())),
        observed_place_ids=tuple(sorted(observed)),
        unmade_opportunity_records=tuple(
            (identifier, count, reason)
            for (identifier, reason), count in sorted(unmade.items())
        ),
        travel_paths=compiler._travel_paths(
            context_origin_cell=skeleton.origin.birth_cell_id,
            visited_place_ids=tuple(sorted(visit_counts)),
            station_place_id=skeleton.earth_transition.departure_place_id,
        ),
    )
    vocation = skeleton.vocation
    if qualified:
        work = next(
            (
                s
                for s in skeleton.life_segments
                if s.kind == "work" and s.vocation_id in qualified
            ),
            None,
        )
        if work is not None:
            vocation = replace(
                vocation,
                vocation_id=work.vocation_id,
                proficiency_band="basic",
                workplace_place_id=work.place_id,
            )
    actual_ids = {a.activity_id for a in completed if a.status == "completed"}
    for segment in skeleton.life_segments:
        referenced = [a for a in completed if segment.segment_id in a.depends_on]
        if referenced and all(a.status == "completed" for a in referenced):
            actual_ids.add(segment.segment_id)
    links = tuple(
        replace(link, status="experienced") if link.source_ref in actual_ids else link
        for link in skeleton.place_links
    )
    known_friend_ids = set(relationships)
    admitted_cores = tuple(
        c
        for c in skeleton.important_friend_families
        if c.protagonist.person_id in known_friend_ids
    )
    for record in proposals:
        if (
            record.source == "important_friend_family"
            and set(record.related_person_ids) <= known_friend_ids
        ):
            relationships[record.person_id] = record
    admitted = {"self", *relationships}
    graph_edges = tuple(
        replace(e, status="established")
        for e in skeleton.relationships
        if {e.subject_id, e.object_id} <= admitted
        and (
            e.status == "established"
            or e.source_ref in actual_ids
            or (e.subject_id == "self" and e.object_id in relationships)
        )
    )
    groups = tuple(
        replace(g, member_ids=tuple(p for p in g.member_ids if p in admitted))
        for g in skeleton.groups
        if (g.source_ref.startswith("family:") or g.source_ref in actual_ids)
        and len({p for p in g.member_ids if p in admitted}) >= 3
    )
    context = replace(
        skeleton,
        important_friend_families=admitted_cores,
        relationships=graph_edges,
        groups=groups,
        mobility=mobility,
        vocation=vocation,
        activities=tuple(completed),
        place_links=links,
        content_hash="",
    )
    return (
        replace(context, content_hash=_content_hash(context)),
        tuple(r for r in relationships.values() if r.source != "adoption_decision")
        + tuple(r for r in relationships.values() if r.source == "adoption_decision"),
        tuple(episodes),
    )
