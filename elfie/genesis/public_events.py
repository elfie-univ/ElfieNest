"""Immutable shared event and learning inputs for personal skeleton generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PublicEventInstance:
    instance_id: str
    years_ago: int
    day_of_year: int
    activities: tuple[str, ...] = ()
    public_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicEventRule:
    event_id: str
    label: str
    recurrence: Literal["annual", "one_time", "explicit_instances"]
    place_ids: tuple[str, ...]
    day_window: tuple[int, int]
    local_year: int | None
    instances: tuple[PublicEventInstance, ...]
    impact_scope: str
    eligible: str
    selection: str
    creates_contact_opportunity: bool
    participation_probability: float
    duration_days: int
    minimum_age_years: int
    required_qualification: str
    activities: tuple[str, ...]
    public_effects: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class PublicEventCatalog:
    days_per_year: int = 196
    events: tuple[PublicEventRule, ...] = ()
    current_local_year: int | None = None
    current_day_of_year: int | None = None


@dataclass(frozen=True)
class VocationRule:
    vocation_id: str
    label: str
    apprenticeship_years: int
    qualification_evidence: tuple[str, ...]


@dataclass(frozen=True)
class LearningPolicy:
    minimum_start_age_years: int = 2
    learning_days_per_year: int = 98
    work_days_per_year: int = 98
    care_days_per_year: int = 49
    vocations: tuple[VocationRule, ...] = ()
