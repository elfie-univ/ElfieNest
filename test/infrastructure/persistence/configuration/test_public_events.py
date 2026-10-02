"""Shared event inputs are typed and integrity-bound before scheduling."""

from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.public_events import (
    load_learning_policy,
    load_public_event_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package

ROOT = Path(__file__).resolve().parents[4] / "config"


def test_registered_events_and_learning_are_loaded() -> None:
    package = load_genesis_source_package(root=ROOT)
    assert "events.yaml" in package.manifest.member_ids
    assert len(package.public_events.events) == 7
    assert package.public_events.days_per_year == 196
    assert package.public_events.current_local_year is None
    assert package.public_events.current_day_of_year is None
    exploration = package.public_events.events[-1]
    assert tuple(item.years_ago for item in exploration.instances) == (1, 3, 5)
    assert package.learning_policy.minimum_start_age_years == 2
    assert package.learning_policy.care_days_per_year == 49
    assert package.learning_policy.vocations[2].apprenticeship_years == 2


def test_event_dates_and_places_are_validated() -> None:
    document = yaml.safe_load((ROOT / "genesis/events.yaml").read_text())
    places = tuple(
        place
        for item in document["events"]
        for place in item["locations"]["place_refs"]
    )
    document["events"][0]["schedule"]["day_of_year"] = 197
    with pytest.raises(ValueError, match="day"):
        load_public_event_catalog(document, place_ids=places)
    document["events"][0]["schedule"]["day_of_year"] = 50
    with pytest.raises(ValueError, match="place"):
        load_public_event_catalog(document, place_ids=())


@pytest.mark.parametrize("probability", [-0.1, 1.1, True])
def test_event_probability_rejects_invalid_values(probability: object) -> None:
    document = yaml.safe_load((ROOT / "genesis/events.yaml").read_text())
    places = tuple(
        place
        for item in document["events"]
        for place in item["locations"]["place_refs"]
    )
    document["events"][0]["participant_policy"]["participation_probability"] = (
        probability
    )
    with pytest.raises(ValueError, match="probability"):
        load_public_event_catalog(document, place_ids=places)


@pytest.mark.parametrize("year,day", [(2026, 197), (2026, None), (None, 32)])
def test_local_time_anchor_requires_valid_explicit_date(
    year: object, day: object
) -> None:
    document = yaml.safe_load((ROOT / "genesis/events.yaml").read_text())
    document["calendar"]["current_local_year"] = year
    document["calendar"]["current_day_of_year"] = day
    with pytest.raises(ValueError, match="anchor|day"):
        load_public_event_catalog(document, place_ids=())


def test_care_budget_must_fit_with_learning_and_work() -> None:
    program = yaml.safe_load((ROOT / "genesis/program.yaml").read_text())
    learning = program["rules"]["learning"]
    learning["care_days_per_year"] = 99
    with pytest.raises(ValueError, match="care budget"):
        load_learning_policy(learning, days_per_year=196)
