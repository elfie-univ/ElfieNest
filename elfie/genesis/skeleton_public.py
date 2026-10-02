"""Resolve shared public event occurrences into personal activity slots."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

from .skeleton import (
    ActivitySlot,
    SkeletonDecision,
    SkeletonPerson,
    SkeletonRelationship,
)
from .skeleton_graph import fresh_contact_name
from .world import ACTIVITY_ELIGIBLE_STAGES

if TYPE_CHECKING:
    from .compiler import GenesisCompileInput, GenesisCompiler, LifeContext


def schedule_public_activities(
    compiler: GenesisCompiler,
    request: GenesisCompileInput,
    context: LifeContext,
    reserve: Callable[[int, int, int | None], int | None],
) -> tuple[
    list[ActivitySlot],
    list[SkeletonPerson],
    list[SkeletonRelationship],
    list[SkeletonDecision],
]:
    from .compiler import stage_for_age

    days = context.days_per_year
    age = context.identity.age_years_at_adoption
    people = list(context.people)
    edges = list(context.relationships)
    slots = []
    decisions = []
    local_year = compiler._source.public_events.current_local_year
    for event in compiler._source.public_events.events:
        occurrences = []
        if event.recurrence == "annual":
            for year in range(event.minimum_age_years, age):
                day = random.Random(
                    compiler._domain_seed(
                        0,
                        f"episodes:public-date:{event.event_id}:years-ago:{age - year}",
                    )
                ).randint(*event.day_window)
                identity = (
                    f"{event.event_id}:{local_year - age + year}"
                    if local_year
                    else f"{event.event_id}:years-ago:{age - year}"
                )
                occurrences.append((year, day, identity))
        elif (
            event.recurrence == "one_time"
            and local_year is not None
            and event.local_year is not None
        ):
            occurrences.append(
                (
                    age - (local_year - event.local_year),
                    event.day_window[0],
                    f"{event.event_id}:{event.local_year}",
                )
            )
        elif event.recurrence == "explicit_instances":
            occurrences.extend(
                (age - i.years_ago, i.day_of_year, i.instance_id)
                for i in event.instances
            )
        if not occurrences:
            decisions.append(
                SkeletonDecision(
                    event.event_id,
                    "public",
                    "not_applicable",
                    "当前年龄或时间锚点没有可用事件实例",
                    "events.yaml",
                )
            )
        for year, day, identity in occurrences:
            reason = ""
            if year < event.minimum_age_years or year >= age:
                reason = "事件不在已完成的适龄生活年份内"
            elif (
                stage_for_age(request.species_id, year, compiler._catalog)
                not in ACTIVITY_ELIGIBLE_STAGES
            ):
                reason = "该生命阶段需要照护，不安排公共活动"
            elif event.required_qualification:
                reason = f"缺少资格证据：{event.required_qualification}"
            elif event.eligible.find("saevi") >= 0 and request.species_id != "saevi":
                reason = "非Saevi族群活动资格"
            elif event.eligible.find("tovren") >= 0 and request.species_id != "tovren":
                reason = "非Tovren族群活动资格"
            elif event.eligible.find("myelle") >= 0 and request.species_id != "myelle":
                reason = "非Myelle族群活动资格"
            distances = {
                p: compiler._opportunity_distance_days(
                    context.origin.birth_cell_id, (p,)
                )
                for p in event.place_ids
            }
            target = min(
                event.place_ids,
                key=lambda p: next(
                    (d for d in (distances[p],) if d is not None), days * days
                ),
            )
            metrics = compiler._opportunity_trip_metrics(
                context.origin.birth_cell_id, (target,), event.duration_days
            )
            if not reason and (
                metrics is None or compiler._place_access(target) == "restricted"
            ):
                reason = "活动地点没有合法可达路线"
            probability = compiler._domain_uniform(
                request.appearance_seed, f"episodes:public-participation:{identity}"
            )
            if not reason and probability >= event.participation_probability:
                reason = "参与概率抽样未选择"
            duration = metrics[1] if metrics else event.duration_days
            # Arrival at the gathering must match its configured day.
            start = day - 1 - (metrics[0] // 2 if metrics else 0)
            if not reason and reserve(year, duration, start) is None:
                reason = "活动往返与学习工作或其他行程时间冲突"
            participant_ids: tuple[str, ...] = ()
            activity_id = f"public:{identity}"
            if not reason and event.creates_contact_opportunity:
                rng = random.Random(
                    compiler._domain_seed(
                        request.appearance_seed, f"episodes:public-contacts:{identity}"
                    )
                )
                policy = compiler._source.generation_policy
                distribution = policy.public_contact_count_distribution
                count = rng.choices(
                    [n for n, _ in distribution], weights=[w for _, w in distribution]
                )[0]
                known_ids = {
                    p
                    for a in context.activities
                    if a.direction == "growth"
                    and a.status != "excluded"
                    and (a.age_year, a.start_day + a.duration_days) <= (year, start)
                    for p in a.participant_ids
                }
                reusable = [
                    p.person_id
                    for p in people
                    if p.person_id in known_ids
                    and p.birth_age_year is not None
                    and 0
                    <= year - p.birth_age_year
                    < compiler._species(
                        {"Saevi": "saevi", "Tovren": "tovren", "Myelle": "myelle"}.get(
                            p.species_id, p.species_id
                        )
                    ).genesis.terminal_age_years
                    and (p.death_age_year is None or p.death_age_year > year)
                ]
                participants = []
                for index in range(count):
                    person_id = f"contact:{identity}:{index}"
                    if (
                        reusable
                        and rng.random() < policy.public_contact_reuse_probability
                    ):
                        person_id = reusable.pop(rng.randrange(len(reusable)))
                    else:
                        people.append(
                            SkeletonPerson(
                                person_id,
                                fresh_contact_name(compiler, request, people),
                                request.species_id,
                                rng.choice(("male", "female")),
                                0,
                                activity_id,
                            )
                        )
                    edges.append(
                        SkeletonRelationship(
                            "self",
                            person_id,
                            "activity_contact",
                            "contact_slot",
                            activity_id,
                        )
                    )
                    participants.append(person_id)
                participant_ids = tuple(participants)
            slots.append(
                ActivitySlot(
                    activity_id,
                    "public",
                    event.label,
                    year,
                    max(0, start),
                    duration,
                    (target,),
                    participant_ids,
                    metrics[2] if metrics else (),
                    (
                        "age_and_species_eligibility",
                        "legal_route",
                        *(
                            [event.required_qualification]
                            if event.required_qualification
                            else []
                        ),
                    ),
                    (),
                    ("participation", "contact", "public_report"),
                    "excluded" if reason else "scheduled",
                    "events.yaml",
                    reason,
                    identity,
                    metrics[0] if metrics else 0,
                    event.duration_days,
                )
            )

    return slots, people, edges, decisions
