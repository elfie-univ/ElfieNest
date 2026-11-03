from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nest.public import EnvironmentSchedule, LifePhase, Nest


def schedule(**changes):
    return EnvironmentSchedule.model_validate(
        {
            "daylight_source": "manual",
            "sunrise_time": "06:00",
            "sunset_time": "18:00",
            "rest_time": "00:00",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "hour,phase",
    [
        (5, LifePhase.NIGHT),
        (6, LifePhase.DAY),
        (18, LifePhase.DUSK),
        (23, LifePhase.DUSK),
    ],
)
def test_three_time_points_define_local_phases(hour, phase):
    moment = datetime(2026, 6, 21, hour, tzinfo=timezone.utc)
    assert schedule().phase_at(moment) is phase


def test_custom_rest_crosses_midnight_and_reaches_formal_nest():
    nest = Nest()
    moment = datetime(2026, 6, 21, 23, tzinfo=timezone.utc)
    nest.tick(0, local_time=moment, environment_schedule=schedule(rest_time="22:30"))
    assert nest.life_phase is LifePhase.NIGHT
    assert nest.desired_environment.quiet_mode
    nest.tick(0, local_time=moment, environment_schedule=schedule(rest_time="01:00"))
    assert nest.life_phase is LifePhase.DUSK
    assert not nest.desired_environment.quiet_mode


@pytest.mark.parametrize(
    "changes",
    [
        {"sunrise_time": "25:00"},
        {"rest_time": "12:00"},
        {"daylight_source": "local"},
        {"latitude": True},
        {"latitude": 91, "longitude": 0},
    ],
)
def test_invalid_or_incomplete_schedules_fail_explicitly(changes):
    with pytest.raises(ValidationError):
        schedule(**changes)


def test_local_solar_times_change_with_date_and_longitude():
    # Public Beijing city coordinates, not a user's device location.
    config = schedule(daylight_source="local", latitude=39.9, longitude=116.4)
    zone = timezone(timedelta(hours=8))
    summer = config.daylight_at(datetime(2026, 6, 21, 12, tzinfo=zone))
    winter = config.daylight_at(datetime(2026, 12, 21, 12, tzinfo=zone))
    assert "04:30" < summer.sunrise_time < "05:00"
    assert "19:30" < summer.sunset_time < "20:00"
    assert winter.sunrise_time > summer.sunrise_time
    assert winter.sunset_time < summer.sunset_time
    assert config.phase_at(datetime(2026, 6, 21, 5, tzinfo=zone)) is LifePhase.DAY


def test_polar_events_are_explicit_and_never_use_stale_manual_times():
    config = schedule(daylight_source="local", latitude=89, longitude=0)
    summer = datetime(2026, 6, 21, tzinfo=timezone.utc)
    winter = datetime(2026, 12, 21, tzinfo=timezone.utc)
    assert config.daylight_at(summer).condition == "polar_day"
    assert config.daylight_at(summer).sunrise_time is None
    assert config.phase_at(summer) is LifePhase.DAY
    assert config.phase_at(winter) is LifePhase.NIGHT
