"""Schedule public occurrences, contact opportunities and journeys together."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .skeleton import (
    ActivitySlot,
    PersonalPlaceLink,
    SkeletonDecision,
)
from .skeleton_graph import FAMILY_ROLES
from .skeleton_public import schedule_public_activities

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext
    from .contracts import GenesisCandidate, RelationshipSeed


def build_activity_skeleton(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    candidate: GenesisCandidate,
    context: LifeContext,
    relationships: tuple[RelationshipSeed, ...],
) -> LifeContext:
    days = context.days_per_year
    age = context.identity.age_years_at_adoption
    occupied: dict[int, list[tuple[int, int]]] = {}
    fixed_starts: dict[tuple[str, int], int] = {}
    for year in range(age + 1):
        active = [
            s
            for s in context.life_segments
            if s.start_age_year <= year < s.end_age_year
        ]
        # Concurrent young children share one household care budget.
        care = max((s.days_per_year for s in active if s.kind == "care"), default=0)
        used = care + sum(s.days_per_year for s in active if s.kind != "care")
        if used > days:
            raise ValueError("固定生活区间超过年度预算")
        if care:
            occupied.setdefault(year, []).append((0, care))
        fixed = [s for s in active if s.kind in {"learning", "work"}]
        cursor = care
        spare = days - used
        for segment in fixed:
            offset = int(
                compiler._domain_uniform(
                    request.appearance_seed,
                    f"learning:schedule:{segment.segment_id}:{year}",
                )
                * (spare + 1)
            )
            block_start = cursor + offset
            fixed_starts[(segment.segment_id, year)] = block_start
            occupied.setdefault(year, []).append(
                (block_start, block_start + segment.days_per_year)
            )
            cursor = block_start + segment.days_per_year
            spare -= offset
    slots: list[ActivitySlot] = []
    links = list(context.place_links)
    decisions = list(context.decisions)
    people = list(context.people)
    edges = list(context.relationships)

    def reserve(year: int, duration: int, fixed: int | None = None) -> int | None:
        windows = sorted(occupied.get(year, []))
        starts = [fixed] if fixed is not None else [0, *[end for _, end in windows]]
        for start in starts:
            if start is None or start < 0 or start + duration > days:
                continue
            if any(start < end and start + duration > begin for begin, end in windows):
                continue
            occupied.setdefault(year, []).append((start, start + duration))
            return start
        return None

    # Fixed apprenticeship/work slots use the time already reserved by their
    # own intervals. Qualification is still withheld until stage four.
    for segment in context.life_segments:
        if segment.kind not in {"learning", "work"}:
            continue
        for year in range(segment.start_age_year, segment.end_age_year):
            slots.append(
                ActivitySlot(
                    f"{segment.segment_id}:{year}",
                    "learning_work",
                    segment.kind,
                    year,
                    fixed_starts[(segment.segment_id, year)],
                    segment.days_per_year,
                    (segment.place_id,),
                    segment.participant_ids,
                    (),
                    (
                        "teacher_and_practice"
                        if segment.kind == "learning"
                        else "apprenticeship_completed",
                    ),
                    (segment.segment_id, "learning:apprenticeship")
                    if segment.kind == "work"
                    else (segment.segment_id,),
                    ("practice_completed", "knowledge_contact"),
                    "scheduled",
                    segment.source_ref,
                )
            )

    # Existing social proposals become contact slots; no padding is added.
    for relation in relationships:
        if relation.role in FAMILY_ROLES:
            continue
        contact_year = relation.relationship_start_age
        if contact_year is None:
            continue
        start = reserve(contact_year, 1)
        place = relation.home_place_id or context.origin.predeparture_home_place_id
        reason = "" if start is not None else "共同生活接触与固定日程冲突"
        slots.append(
            ActivitySlot(
                f"contact:{relation.person_id}",
                "growth",
                "shared_life_contact",
                contact_year,
                start or 0,
                1,
                (place,),
                (relation.person_id,),
                (),
                ("shared_residence",),
                ("residence:home",),
                ("acquaintance", "no_relationship"),
                "scheduled" if not reason else "excluded",
                relation.source_ref,
                reason,
            )
        )

    public_slots, people, edges, public_decisions = schedule_public_activities(
        compiler, request, replace(context, activities=tuple(slots)), reserve
    )
    slots.extend(public_slots)
    decisions.extend(public_decisions)

    planned = compiler._personal_mobility(
        request, candidate, context, relationships
    ).mobility
    ages = dict(planned.visit_age_years)
    for opportunity_id, places, _count, purpose, stay in planned.opportunity_records:
        travel = dict(planned.opportunity_travel_days).get(opportunity_id, 0)
        routes = dict(planned.opportunity_route_ids).get(opportunity_id, ())
        for index, year in enumerate(ages.get(opportunity_id, ())):
            reason = ""
            start = reserve(year, travel + stay)
            if start is None:
                reason = "旅游探索与固定生活或公共活动日程冲突"
            slot_id = f"travel:{opportunity_id}:{index}"
            slots.append(
                ActivitySlot(
                    slot_id,
                    "travel",
                    purpose,
                    year,
                    start or 0,
                    travel + stay,
                    places if index == 0 else places[:1],
                    (),
                    routes,
                    ("legal_route", "annual_budget"),
                    (),
                    ("visited", "witnessed"),
                    "excluded" if reason else "scheduled",
                    f"visit-opportunity:{opportunity_id}",
                    reason,
                    travel_days=travel,
                    stay_days=stay,
                    observed_place_ids=tuple(
                        p
                        for p in places
                        if compiler._place_access(p) == "observation_only"
                    ),
                )
            )
    for opportunity_id, count, reason in planned.unmade_opportunity_records:
        decisions.append(
            SkeletonDecision(
                opportunity_id,
                "travel",
                "excluded",
                f"{count}次：{reason}",
                "rules.policy.visits",
            )
        )
    selected = {r[0] for r in planned.opportunity_records} | {
        r[0] for r in planned.unmade_opportunity_records
    }
    for rule in compiler._source.generation_policy.visit_opportunities:
        if rule.opportunity_id not in selected:
            decisions.append(
                SkeletonDecision(
                    rule.opportunity_id,
                    "travel",
                    "not_selected",
                    "年龄、地区、前置机会、可达性或概率抽样未选中",
                    "rules.policy.visits",
                )
            )
    station = context.earth_transition.departure_place_id
    path = compiler._land_path_to_place(context.origin.birth_cell_id, station)
    path_routes = compiler._registered_routes_on_path(path)
    trip = compiler._opportunity_trip_metrics(
        context.origin.birth_cell_id, (station,), 0
    )
    travel = trip[0] // 2 if trip else 0
    duration = travel + context.earth_transition.preparation_duration_local_days
    start = reserve(age, duration)
    if start is None:
        raise ValueError("赴地准备和行程无法排入当前年份")
    slots.append(
        ActivitySlot(
            "departure:preparation",
            "departure",
            "赴地",
            age,
            start,
            duration,
            (station,),
            (),
            path_routes,
            ("invitation_accepted", "care_compatible"),
            (),
            ("preparation_completed", "departed"),
            "scheduled",
            "rules.arrival",
            travel_days=travel,
            stay_days=context.earth_transition.preparation_duration_local_days,
        )
    )
    for slot in slots:
        if slot.status == "scheduled":
            links.extend(
                PersonalPlaceLink(
                    p,
                    slot.purpose,
                    slot.age_year,
                    slot.age_year,
                    "planned",
                    slot.activity_id,
                )
                for p in slot.place_ids
            )
    empty = replace(
        context.mobility,
        visited_place_ids=(),
        familiar_route_ids=(),
        visit_counts=(),
        visit_purposes=(),
        visit_stay_days=(),
        visit_age_years=(),
        observed_place_ids=(),
        opportunity_records=(),
        opportunity_route_ids=(),
        opportunity_travel_days=(),
        unmade_opportunity_records=planned.unmade_opportunity_records,
        travel_paths=(),
    )
    return replace(
        context,
        people=tuple(people),
        relationships=tuple(edges),
        activities=tuple(
            sorted(slots, key=lambda s: (s.age_year, s.start_day, s.activity_id))
        ),
        place_links=tuple(links),
        decisions=tuple(decisions),
        mobility=empty,
        content_hash="",
    )
