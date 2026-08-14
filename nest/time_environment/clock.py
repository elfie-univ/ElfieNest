"""Deterministic household time and environment owner."""

from __future__ import annotations

from dataclasses import dataclass, field

from nest.state.models import (
    EnvironmentActualState,
    EnvironmentDesiredState,
    EnvironmentRule,
    LifePhase,
)


@dataclass
class TimeEnvironmentState:
    elapsed_seconds: float = 0.0
    clock_paused: bool = False
    time_scale: float = 1.0
    environment_desired: EnvironmentDesiredState = field(
        default_factory=EnvironmentDesiredState
    )
    environment_actual: EnvironmentActualState | None = None
    environment_rules: tuple[EnvironmentRule, ...] = ()

    @property
    def life_phase(self) -> LifePhase:
        hour = (self.elapsed_seconds % 86400.0) / 3600.0
        if hour < 6.0 or hour >= 20.0:
            return LifePhase.NIGHT
        if hour < 8.0:
            return LifePhase.DAWN
        if hour < 18.0:
            return LifePhase.DAY
        return LifePhase.DUSK

    def advance(self, seconds: float) -> None:
        if self.clock_paused:
            return
        self.elapsed_seconds += seconds * self.time_scale
        self.apply_environment_rules()

    def set_environment_desired(self, desired: EnvironmentDesiredState) -> None:
        self.environment_desired = desired

    def set_environment_rules(self, rules: tuple[EnvironmentRule, ...]) -> None:
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("environment rule ids must be unique")
        self.environment_rules = rules
        self.apply_environment_rules()

    def apply_environment_rules(self) -> None:
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


__all__ = ("TimeEnvironmentState",)
