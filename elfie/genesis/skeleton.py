"""Transient graph records shared by the five life-skeleton directions.

Times use local age-years and zero-based local days, not invented birthdays.
Public graph records remain references to the published package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from elfie.brain.memory.memory_records import AssertionInput, NodeInput

if TYPE_CHECKING:
    from .compiler import LifeContext


@dataclass(frozen=True)
class SkeletonPerson:
    person_id: str
    display_name: str
    species_id: str
    gender: str
    birth_age_year: int | None
    source_ref: str
    home_place_id: str = ""
    death_age_year: int | None = None


@dataclass(frozen=True)
class SkeletonGroup:
    group_id: str
    kind: str
    label: str
    member_ids: tuple[str, ...]
    source_ref: str


@dataclass(frozen=True)
class SkeletonRelationship:
    subject_id: str
    object_id: str
    relation: str
    status: Literal["established", "contact_slot"]
    source_ref: str
    label: str = ""
    relationship_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkeletonPlace:
    place_id: str
    label: str
    parent_id: str
    source_ref: str


@dataclass(frozen=True)
class PersonalPlaceLink:
    place_id: str
    purpose: str
    start_age_year: int
    end_age_year: int
    status: Literal["established", "planned", "experienced"]
    source_ref: str


@dataclass(frozen=True)
class LifeSegment:
    segment_id: str
    kind: Literal["residence", "care", "learning", "work"]
    start_age_year: int
    end_age_year: int
    place_id: str
    participant_ids: tuple[str, ...]
    days_per_year: int
    source_ref: str
    vocation_id: str = ""
    required_years: int = 0


@dataclass(frozen=True)
class ActivitySlot:
    activity_id: str
    direction: Literal["public", "travel", "learning_work", "growth", "departure"]
    purpose: str
    age_year: int
    start_day: int
    duration_days: int
    place_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    prerequisites: tuple[str, ...]
    depends_on: tuple[str, ...]
    allowed_outcomes: tuple[str, ...]
    status: Literal["scheduled", "excluded", "completed"]
    source_ref: str
    reason: str = ""
    event_instance_id: str = ""
    travel_days: int = 0
    stay_days: int = 0
    observed_place_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkeletonKnowledge:
    knowledge_id: str
    prerequisite_ids: tuple[str, ...]
    related_ids: tuple[str, ...]
    source_ref: str
    acquisition_conditions: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    graph_nodes: tuple[NodeInput, ...] = ()
    graph_assertions: tuple[AssertionInput, ...] = ()


@dataclass(frozen=True)
class SkeletonDecision:
    object_id: str
    direction: str
    outcome: str
    reason: str
    source_ref: str


def validate_skeleton(context: LifeContext) -> None:
    """Validate references and one calendar before generating any Episode."""

    def unique(values: list[str], label: str) -> set[str]:
        if len(values) != len(set(values)):
            raise ValueError(f"骨架{label}ID重复")
        return set(values)

    people = unique([p.person_id for p in context.people], "人物")
    places = unique([p.place_id for p in context.places], "地点")
    segments = unique([s.segment_id for s in context.life_segments], "区间")
    activities = unique([a.activity_id for a in context.activities], "活动")
    activity_by_id = {a.activity_id: a for a in context.activities}
    person_by_id = {p.person_id: p for p in context.people}
    routes = {r.route_id for r in context.routes}
    knowledge = unique([k.knowledge_id for k in context.knowledge_nodes], "知识")
    current_age = context.identity.age_years_at_adoption
    days = context.days_per_year
    unique([g.group_id for g in context.groups], "群组")
    named_pairs = {
        (e.subject_id, e.object_id)
        for e in context.relationships
        if e.label
        and e.source_ref
        and len(e.relationship_path) >= 2
        and e.relationship_path[0] == e.subject_id
        and e.relationship_path[-1] == e.object_id
        and set(e.relationship_path) <= people
    }
    for group in context.groups:
        if (
            len(set(group.member_ids)) < 3
            or not group.source_ref
            or not set(group.member_ids) <= people
        ):
            raise ValueError("骨架群组成员引用或来源不存在")
        if any(
            (a, b) not in named_pairs
            for a in group.member_ids
            for b in group.member_ids
            if a != b
        ):
            raise ValueError("骨架群组缺少两两关系、称谓或证明路径")
    for edge in context.relationships:
        if edge.subject_id not in people or edge.object_id not in people:
            raise ValueError("骨架关系人物引用不存在")
    for place_edge in context.place_relations:
        if place_edge.subject_id not in places or place_edge.object_id not in places:
            raise ValueError("骨架地点关系引用不存在")
    for node in context.knowledge_nodes:
        if not set(node.prerequisite_ids) <= knowledge:
            raise ValueError("骨架知识前提引用不存在")
    for link in context.place_links:
        if link.place_id not in places or not link.source_ref:
            raise ValueError("骨架个人地点引用或来源不存在")
    for segment in context.life_segments:
        if not 0 <= segment.start_age_year <= segment.end_age_year <= current_age:
            raise ValueError("骨架生活区间越界")
        if segment.place_id not in places or not set(segment.participant_ids) <= people:
            raise ValueError("骨架生活区间人物或地点引用不存在")
        if not 0 <= segment.days_per_year <= days or not segment.source_ref:
            raise ValueError("骨架区间预算或来源无效")
    occupied: list[tuple[int, int, int]] = []
    for activity in context.activities:
        if (
            not set(activity.place_ids) <= places
            or not set(activity.participant_ids) <= people
        ):
            raise ValueError("骨架活动人物或地点引用不存在")
        if not set(activity.route_ids) <= routes:
            raise ValueError("骨架活动路线引用不存在")
        if not set(activity.depends_on) <= (activities | segments):
            raise ValueError("骨架活动依赖不存在")
        if not activity.source_ref or not activity.allowed_outcomes:
            raise ValueError("骨架活动缺来源或允许结果")
        if activity.status == "excluded":
            if not activity.reason:
                raise ValueError("排除活动缺少原因")
            continue
        if not 0 <= activity.age_year <= current_age:
            raise ValueError("骨架活动年龄越界")
        end = activity.start_day + activity.duration_days
        if activity.start_day < 0 or activity.duration_days <= 0 or end > days:
            raise ValueError("骨架活动超出本地年")
        for person_id in activity.participant_ids:
            birth = person_by_id[person_id].birth_age_year
            death = person_by_id[person_id].death_age_year
            if death is not None and death <= activity.age_year:
                raise ValueError("骨架活动人物已去世")
            if birth is not None and birth > activity.age_year:
                raise ValueError("骨架活动人物尚未出生")
        for dependency_id in activity.depends_on:
            dependency = activity_by_id.get(dependency_id)
            if dependency is not None:
                dependency_end = (
                    dependency.age_year * days
                    + dependency.start_day
                    + dependency.duration_days
                )
                if (
                    dependency.status == "excluded"
                    or dependency_end > activity.age_year * days + activity.start_day
                ):
                    raise ValueError("骨架活动前置依赖尚未完成")
        active = [
            s
            for s in context.life_segments
            if s.start_age_year <= activity.age_year < s.end_age_year
        ]
        care = max((s.days_per_year for s in active if s.kind == "care"), default=0)
        if activity.start_day < care:
            raise ValueError("骨架活动与固定区间时间冲突")
        for age, start, stop in occupied:
            if age == activity.age_year and activity.start_day < stop and end > start:
                raise ValueError("骨架活动时间冲突")
        occupied.append((activity.age_year, activity.start_day, end))
