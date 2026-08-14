"""Nest 运行状态存储。"""

from __future__ import annotations

from nest.rules.living import LivingRulesState
from nest.space.catalog import SpaceFacilitiesState
from nest.state.config import NestConfig
from nest.state.errors import (
    BedConflictError,
    NoHomeAvailableError,
    ReconciliationRequiredError,
    UnknownAnchorError,
    UnknownResidentError,
)
from nest.state.models import (
    EnvironmentActualState,
    EnvironmentDesiredState,
    EnvironmentRule,
    HomeAssignment,
    LifePhase,
    RuntimeResidentMirror,
    WorldCatalog,
)
from nest.time_environment.clock import TimeEnvironmentState


class NestState:
    """Compatibility shell composing the four concrete Nest owner states."""

    def __init__(self, config: NestConfig) -> None:
        self.config = config
        self.space = SpaceFacilitiesState()
        self.living_rules = LivingRulesState.create(self.space)
        self.time_environment = TimeEnvironmentState()

    @property
    def residents(self):
        return self.living_rules.residents

    @property
    def home_assignments(self):
        return self.living_rules.home_assignments

    @property
    def runtime_mirrors(self):
        return self.living_rules.runtime_mirrors

    @property
    def reconciliation_required(self) -> bool:
        return self.living_rules.reconciliation_required

    @reconciliation_required.setter
    def reconciliation_required(self, value: bool) -> None:
        self.living_rules.reconciliation_required = value

    @property
    def world_catalog(self):
        return self.space.world_catalog

    @world_catalog.setter
    def world_catalog(self, catalog: WorldCatalog | None) -> None:
        self.space.world_catalog = catalog

    @property
    def elapsed_seconds(self) -> float:
        return self.time_environment.elapsed_seconds

    @elapsed_seconds.setter
    def elapsed_seconds(self, value: float) -> None:
        self.time_environment.elapsed_seconds = value

    @property
    def clock_paused(self) -> bool:
        return self.time_environment.clock_paused

    @clock_paused.setter
    def clock_paused(self, value: bool) -> None:
        self.time_environment.clock_paused = value

    @property
    def time_scale(self) -> float:
        return self.time_environment.time_scale

    @time_scale.setter
    def time_scale(self, value: float) -> None:
        self.time_environment.time_scale = value

    @property
    def environment_desired(self):
        return self.time_environment.environment_desired

    @environment_desired.setter
    def environment_desired(self, value: EnvironmentDesiredState) -> None:
        self.time_environment.environment_desired = value

    @property
    def environment_actual(self):
        return self.time_environment.environment_actual

    @environment_actual.setter
    def environment_actual(self, value: EnvironmentActualState | None) -> None:
        self.time_environment.environment_actual = value

    @property
    def environment_rules(self):
        return self.time_environment.environment_rules

    @environment_rules.setter
    def environment_rules(self, value) -> None:
        self.time_environment.environment_rules = value

    def register_resident(self, elfie_id: str) -> None:
        self.living_rules.register_resident(elfie_id)

    def remove_resident(self, elfie_id: str) -> None:
        self.living_rules.remove_resident(elfie_id)

    def update_resident(
        self,
        elfie_id: str,
        posture: str,
    ) -> None:
        self.living_rules.update_resident(elfie_id, posture)

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        self.space.apply_catalog(catalog)
        self.living_rules.apply_catalog()

    def admit_resident(self, elfie_id: str) -> HomeAssignment:
        return self.living_rules.admit_resident(elfie_id)

    def assign_home(self, elfie_id: str, anchor_id: str) -> HomeAssignment:
        return self.living_rules.assign_home(elfie_id, anchor_id)

    def release_home(self, elfie_id: str) -> None:
        self.living_rules.release_home(elfie_id)

    def home_anchor_id(self, elfie_id: str) -> str | None:
        return self.living_rules.home_anchor_id(elfie_id)

    def apply_runtime_mirrors(
        self,
        mirrors: tuple[RuntimeResidentMirror, ...],
    ) -> None:
        self.living_rules.apply_runtime_mirrors(mirrors)

    @property
    def life_phase(self) -> LifePhase:
        return self.time_environment.life_phase

    def set_environment_desired(self, desired: EnvironmentDesiredState) -> None:
        self.time_environment.set_environment_desired(desired)

    def set_environment_rules(self, rules: tuple[EnvironmentRule, ...]) -> None:
        self.time_environment.set_environment_rules(rules)

    def apply_environment_rules(self) -> None:
        self.time_environment.apply_environment_rules()


__all__ = (
    "BedConflictError",
    "NestState",
    "NoHomeAvailableError",
    "ReconciliationRequiredError",
    "UnknownAnchorError",
    "UnknownResidentError",
)
