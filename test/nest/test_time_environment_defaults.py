"""Default lighting follows the existing Nest clock and override owner."""

import pytest

from nest import Nest
from nest.public import EnvironmentDesiredState, LifePhase


@pytest.mark.parametrize(
    ("hour", "phase", "lights_on", "quiet"),
    [
        (0, LifePhase.NIGHT, True, True),
        (5.999, LifePhase.NIGHT, True, True),
        (6, LifePhase.DAY, False, False),
        (17.999, LifePhase.DAY, False, False),
        (18, LifePhase.DUSK, True, False),
        (23.999, LifePhase.DUSK, True, False),
        (24, LifePhase.NIGHT, True, True),
        (32, LifePhase.DAY, False, False),
    ],
)
def test_new_nest_uses_night_only_default_lighting(
    hour: float, phase: LifePhase, lights_on: bool, quiet: bool
) -> None:
    nest = Nest()

    nest.tick(hour * 3600)

    assert nest.life_phase is phase
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=lights_on, quiet_mode=quiet
    )


def test_explicit_override_survives_default_phase_changes_until_cleared() -> None:
    nest = Nest()
    override = EnvironmentDesiredState(lights_on=True, quiet_mode=True)
    nest.set_environment_override(override)

    nest.tick(12 * 3600)
    assert nest.desired_environment == override

    nest.clear_environment_override()
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=False, quiet_mode=False
    )


def test_default_schedule_round_trips_without_replacing_explicit_empty_rules() -> None:
    original = Nest()
    original.tick(12 * 3600)
    restored = Nest()
    restored.restore_snapshot(original.export_snapshot())
    restored.tick(8 * 3600)
    assert restored.desired_environment.lights_on is True

    # An explicit empty schedule is a valid existing persisted choice, not
    # permission to silently replace it with the new-instance defaults.
    original.set_environment_rules(())
    original.set_desired_environment(
        EnvironmentDesiredState(lights_on=True, quiet_mode=True)
    )
    restored.restore_snapshot(original.export_snapshot())
    restored.tick(1 * 3600)
    assert restored.desired_environment == original.desired_environment


def test_new_snapshot_keeps_the_owner_default_schedule() -> None:
    from nest.snapshot import NestSnapshot

    restored = Nest()
    restored.restore_snapshot(
        NestSnapshot(
            desired_bed_count=32,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )
    )
    restored.tick(12 * 3600)

    assert restored.desired_environment.lights_on is False


def test_local_civil_time_does_not_replace_elapsed_lifetime() -> None:
    from datetime import datetime, timedelta, timezone

    nest = Nest()
    local = datetime(2026, 10, 27, 18, tzinfo=timezone(timedelta(hours=8)))
    nest.tick(1.5, local_time=local)
    assert nest.elapsed_seconds == 1.5
    assert nest.life_phase is LifePhase.DUSK
    assert nest.desired_environment.quiet_mode is False
    nest.tick(1.5, local_time=local.replace(hour=0))
    assert nest.elapsed_seconds == 3.0
    assert nest.desired_environment.quiet_mode is True
    nest.pause_clock()
    nest.tick(10, local_time=local.replace(hour=12))
    assert nest.elapsed_seconds == 3.0
    assert nest.desired_environment.quiet_mode is True
