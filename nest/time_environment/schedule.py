"""Household daylight policy and deterministic local solar calculations."""

from __future__ import annotations

import calendar
import math
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nest.time_environment.models import LifePhase

_CLOCK = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _clock(minutes: float) -> str:
    value = round(minutes) % 1440
    return f"{value // 60:02d}:{value % 60:02d}"


class DaylightTimes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str
    timezone: str
    sunrise_time: Optional[str]
    sunset_time: Optional[str]
    condition: Literal["normal", "polar_day", "polar_night"]


class EnvironmentSchedule(BaseModel):
    """Three clock points; automatic daylight never changes the rest point."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    daylight_source: Literal["manual", "local"]
    sunrise_time: str = Field(pattern=_CLOCK)
    sunset_time: str = Field(pattern=_CLOCK)
    rest_time: str = Field(pattern=_CLOCK)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(
        default=None, ge=-180, le=180, allow_inf_nan=False
    )

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def _numeric_coordinate(cls, value: object) -> object:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError("coordinates must be finite numbers")
        return value

    @model_validator(mode="after")
    def _valid_points(self) -> EnvironmentSchedule:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.daylight_source == "local" and self.latitude is None:
            raise ValueError("local daylight requires a location")
        if self.daylight_source == "manual":
            start = _minutes(self.sunrise_time)
            sunset = (_minutes(self.sunset_time) - start) % 1440
            rest = (_minutes(self.rest_time) - start) % 1440
            if not 0 < sunset < rest < 1440:
                raise ValueError(
                    "clock points must follow sunrise, sunset, rest, then next sunrise"
                )
        return self

    def daylight_at(self, moment: datetime) -> DaylightTimes:
        offset = moment.utcoffset()
        if offset is None:
            raise ValueError("local time must include its timezone")
        sunrise, sunset = self.sunrise_time, self.sunset_time
        condition: Literal["normal", "polar_day", "polar_night"] = "normal"
        if self.daylight_source == "local":
            # NOAA's published solar equations; no location or date leaves this process.
            # https://gml.noaa.gov/grad/solcalc/solareqns.PDF
            assert self.latitude is not None and self.longitude is not None
            days = 366 if calendar.isleap(moment.year) else 365
            angle = math.tau * (moment.timetuple().tm_yday - 1) / days
            equation = 229.18 * (
                0.000075
                + 0.001868 * math.cos(angle)
                - 0.032077 * math.sin(angle)
                - 0.014615 * math.cos(2 * angle)
                - 0.040849 * math.sin(2 * angle)
            )
            declination = (
                0.006918
                - 0.399912 * math.cos(angle)
                + 0.070257 * math.sin(angle)
                - 0.006758 * math.cos(2 * angle)
                + 0.000907 * math.sin(2 * angle)
                - 0.002697 * math.cos(3 * angle)
                + 0.00148 * math.sin(3 * angle)
            )
            latitude = math.radians(max(-89.999999, min(89.999999, self.latitude)))
            cosine = math.cos(math.radians(90.833)) / (
                math.cos(latitude) * math.cos(declination)
            ) - math.tan(latitude) * math.tan(declination)
            if abs(cosine) > 1:
                condition = "polar_night" if cosine > 1 else "polar_day"
                return DaylightTimes(
                    date=moment.date().isoformat(),
                    timezone=moment.tzname() or "",
                    sunrise_time=None,
                    sunset_time=None,
                    condition=condition,
                )
            hour_angle = math.degrees(math.acos(cosine))
            noon = 720 - 4 * self.longitude - equation + offset.total_seconds() / 60
            sunrise, sunset = (
                _clock(noon - 4 * hour_angle),
                _clock(noon + 4 * hour_angle),
            )
        return DaylightTimes(
            date=moment.date().isoformat(),
            timezone=moment.tzname() or "",
            sunrise_time=sunrise,
            sunset_time=sunset,
            condition=condition,
        )

    def phase_at(self, moment: datetime) -> LifePhase:
        times = self.daylight_at(moment)
        if times.condition == "polar_day":
            return LifePhase.DAY
        if times.condition == "polar_night":
            return LifePhase.NIGHT
        assert times.sunrise_time is not None and times.sunset_time is not None
        start = _minutes(times.sunrise_time)
        current = (moment.hour * 60 + moment.minute + moment.second / 60 - start) % 1440
        sunset = (_minutes(times.sunset_time) - start) % 1440
        rest = (_minutes(self.rest_time) - start) % 1440
        if current < sunset:
            return LifePhase.DAY
        return LifePhase.NIGHT if current >= rest else LifePhase.DUSK
