"""Deterministic household time and environment owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from nest.time_environment.models import (
    EnvironmentDesiredState,
    EnvironmentRule,
    LifePhase,
)


class InvalidTickError(ValueError):
    """Reject negative clock steps and invalid time scales."""

    def __init__(self, seconds: float) -> None:
        super().__init__(seconds)
        self.seconds = seconds

    def __str__(self) -> str:
        return f"tick 时长不能为负数: {self.seconds}"


class TimeEnvironmentDriver:
    """Advance the Nest-owned clock and scheduled environment rules."""

    def __init__(self, state: TimeEnvironmentState) -> None:
        self._state = state

    def tick(
        self,
        seconds: float,
        *,
        environment_override: EnvironmentDesiredState | None = None,
        local_time: datetime | None = None,
    ) -> None:
        if seconds < 0:
            raise InvalidTickError(seconds)
        if self._state.clock_paused:
            return
        if local_time is not None:
            if local_time.utcoffset() is None:
                raise ValueError("local_time must include its local timezone")
            self._state.local_seconds = (
                local_time.hour * 3600
                + local_time.minute * 60
                + local_time.second
                + local_time.microsecond / 1_000_000
            )
        self._state.elapsed_seconds += seconds * self._state.time_scale
        self._state.apply_environment_rules(
            environment_override=environment_override,
        )


def default_environment_rules() -> tuple[EnvironmentRule, ...]:
    """Use the Nest clock for ordinary lights; overrides remain explicit."""
    return tuple(
        EnvironmentRule(
            rule_id=f"default-lighting-{phase.value}",
            phase=phase,
            lights_on=phase in {LifePhase.DUSK, LifePhase.NIGHT},
            quiet_mode=phase is LifePhase.NIGHT,
        )
        for phase in LifePhase
    )


def default_environment_desired() -> EnvironmentDesiredState:
    """The initial simulation time is midnight, already in quiet hours."""
    return EnvironmentDesiredState(lights_on=True, quiet_mode=True)


@dataclass
class TimeEnvironmentState:
    elapsed_seconds: float = 0.0
    # A fresh host-clock input, supplied by App; elapsed lifetime stays durable.
    local_seconds: float | None = None
    clock_paused: bool = False
    time_scale: float = 1.0
    environment_desired: EnvironmentDesiredState = field(
        default_factory=default_environment_desired
    )
    environment_rules: tuple[EnvironmentRule, ...] = field(
        default_factory=default_environment_rules
    )

    @property
    def life_phase(self) -> LifePhase:
        seconds = (
            self.elapsed_seconds if self.local_seconds is None else self.local_seconds
        )
        hour = (seconds % 86400.0) / 3600.0
        if hour < 6.0:
            return LifePhase.NIGHT
        if hour < 18.0:
            return LifePhase.DAY
        return LifePhase.DUSK

    def advance(
        self,
        seconds: float,
        *,
        environment_override: EnvironmentDesiredState | None = None,
    ) -> None:
        if self.clock_paused:
            return
        self.elapsed_seconds += seconds * self.time_scale
        self.apply_environment_rules(environment_override=environment_override)

    def set_environment_desired(self, desired: EnvironmentDesiredState) -> None:
        self.environment_desired = desired

    def set_environment_rules(
        self,
        rules: tuple[EnvironmentRule, ...],
        *,
        environment_override: EnvironmentDesiredState | None = None,
    ) -> None:
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("environment rule ids must be unique")
        self.environment_rules = rules
        self.apply_environment_rules(environment_override=environment_override)

    def apply_environment_rules(
        self,
        *,
        environment_override: EnvironmentDesiredState | None = None,
    ) -> None:
        if environment_override is not None:
            self.environment_desired = environment_override
            return
        matching = [
            rule for rule in self.environment_rules if rule.phase is self.life_phase
        ]
        if not matching:
            return
        rule = matching[-1]
        self.environment_desired = EnvironmentDesiredState(
            lights_on=rule.lights_on,
            quiet_mode=rule.quiet_mode,
        )


__all__ = ("InvalidTickError", "TimeEnvironmentDriver", "TimeEnvironmentState")
