"""Decode package members without making personal participation decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from elfie.genesis.public_events import (
    LearningPolicy,
    PublicEventCatalog,
    PublicEventInstance,
    PublicEventRule,
    VocationRule,
)


def _strings(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(not isinstance(x, str) or not x for x in raw):
        raise ValueError("Expected nonempty string list")
    return tuple(raw)


def _integer(raw: Any, name: str, minimum: int = 0) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < minimum:
        raise ValueError(f"Invalid {name}")
    return raw


def _text(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("Expected nonempty text")
    return raw


def load_public_event_catalog(
    document: Mapping[str, Any], *, place_ids: tuple[str, ...]
) -> PublicEventCatalog:
    if document.get("document_kind") != "public_event_catalog":
        raise ValueError("Expected public event catalog")
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported public event schema")
    if document["scope"]["public_only"] is not True:
        raise ValueError("Event catalog must contain public events only")
    days = _integer(document["calendar"]["days_per_year"], "days_per_year", 1)
    calendar = document["calendar"]
    current_year = calendar.get("current_local_year")
    current_day = calendar.get("current_day_of_year")
    if current_year is not None:
        current_year = _integer(current_year, "current_local_year")
    if current_day is not None:
        current_day = _integer(current_day, "current_day_of_year", 1)
        if current_day > days:
            raise ValueError("Invalid current_day_of_year")
    if (current_year is None) != (current_day is None):
        raise ValueError("Local calendar anchor requires both year and day")
    events = []
    for raw in document["events"]:
        schedule = raw["schedule"]
        recurrence = schedule["recurrence"]
        if recurrence not in {"annual", "one_time", "explicit_instances"}:
            raise ValueError("Unsupported event recurrence")
        if recurrence == "one_time":
            window = (schedule["date"]["day_of_year"],) * 2
            year = _integer(schedule["date"]["local_year"], "local_year")
        elif recurrence == "annual":
            if schedule.get("occurrences_per_year", 1) != 1:
                raise ValueError("Annual events require one occurrence per year")
            window = (
                (schedule["day_of_year"],) * 2
                if "day_of_year" in schedule
                else tuple(schedule["window"]["day_of_year"])
            )
            year = None
        else:
            window, year = (1, days), None
        if (
            len(window) != 2
            or any(_integer(day, "day", 1) > days for day in window)
            or window[0] > window[1]
        ):
            raise ValueError("Invalid public event day window")
        instances = tuple(
            PublicEventInstance(
                instance_id=_text(item["id"]),
                years_ago=_integer(item["years_ago"], "years_ago"),
                day_of_year=_integer(item["day_of_year"], "day", 1),
                activities=_strings(item.get("activities", [])),
                public_effects=_strings(item.get("public_effects", [])),
            )
            for item in schedule.get("instances", [])
        )
        if recurrence == "explicit_instances" and not instances:
            raise ValueError("Explicit events require instances")
        if any(item.day_of_year > days for item in instances):
            raise ValueError("Invalid instance day")
        if len({item.instance_id for item in instances}) != len(instances):
            raise ValueError("Duplicate event instance")
        places = _strings(raw["locations"]["place_refs"])
        if not places or set(places) - set(place_ids):
            raise ValueError("Unknown public event place")
        policy = raw["participant_policy"]
        probability = policy["participation_probability"]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError("Invalid participation probability")
        if not 0 <= probability <= 1:
            raise ValueError("Invalid participation probability")
        duration = _integer(policy["duration_days"], "duration_days", 1)
        if duration > days:
            raise ValueError("Public event duration exceeds local year")
        if not isinstance(policy["creates_contact_opportunity"], bool):
            raise ValueError("Contact opportunity must be boolean")
        events.append(
            PublicEventRule(
                event_id=_text(raw["id"]),
                label=_text(raw["label_zh"]),
                recurrence=cast(Any, recurrence),
                place_ids=places,
                day_window=cast(tuple[int, int], window),
                local_year=year,
                instances=instances,
                impact_scope=_text(raw["impact_scope"]),
                eligible=_text(policy["eligible"]),
                selection=_text(policy["selection"]),
                creates_contact_opportunity=policy["creates_contact_opportunity"],
                participation_probability=float(probability),
                duration_days=duration,
                minimum_age_years=_integer(
                    policy["minimum_age_years"], "minimum_age_years"
                ),
                required_qualification=(
                    _text(policy["required_qualification"])
                    if "required_qualification" in policy
                    else ""
                ),
                activities=_strings(
                    raw.get("activities", raw.get("common_activities", []))
                ),
                public_effects=_strings(
                    raw.get("public_effects", raw.get("common_public_effects", []))
                ),
                source_refs=_strings(raw["source_refs"]),
            )
        )
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("Duplicate public event")
    return PublicEventCatalog(
        days_per_year=days,
        events=tuple(events),
        current_local_year=current_year,
        current_day_of_year=current_day,
    )


def load_learning_policy(
    document: Mapping[str, Any], *, days_per_year: int
) -> LearningPolicy:
    learning = _integer(document["learning_days_per_year"], "learning_days_per_year", 1)
    work = _integer(document["work_days_per_year"], "work_days_per_year", 1)
    care = _integer(document["care_days_per_year"], "care_days_per_year")
    if max(learning, work) >= days_per_year:
        raise ValueError("Learning/work budget must leave free days")
    if max(learning, work) + care > days_per_year:
        raise ValueError("Learning/work and care budget exceed local year")
    vocations = tuple(
        VocationRule(
            vocation_id=_text(item["id"]),
            label=_text(item["name"]),
            apprenticeship_years=_integer(
                item["apprenticeship_years"], "apprenticeship_years", 1
            ),
            qualification_evidence=_strings(item["qualification_evidence"]),
        )
        for item in document["vocations"]
    )
    if len({item.vocation_id for item in vocations}) != len(vocations):
        raise ValueError("Duplicate vocation")
    return LearningPolicy(
        minimum_start_age_years=_integer(
            document["minimum_start_age_local_years"], "minimum_start_age_local_years"
        ),
        learning_days_per_year=learning,
        work_days_per_year=work,
        care_days_per_year=care,
        vocations=vocations,
    )
