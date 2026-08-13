"""Characterization and explicit-clock tests for homeostasis."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.energy.energy import EnergySystem, EnergyTimeRegressionError


def test_update_clock_depletes_awake_state_by_exact_delta() -> None:
    # Given: the existing awake default state.
    energy = EnergySystem()

    # When: the compatibility clock API advances ten seconds.
    energy.update_clock(10.0)

    # Then: existing depletion and accumulation formulas remain unchanged.
    assert energy.get_energy() == pytest.approx(99.95)
    assert energy.get_fatigue() == pytest.approx(0.03)


def test_snapshot_advances_to_absolute_simulation_time() -> None:
    # Given: homeostasis initialized at a deterministic simulation instant.
    energy = EnergySystem(clock=lambda: 100.0)

    # When: a snapshot is requested five seconds later.
    snapshot = energy.snapshot(105.0)

    # Then: state, revision, and capture time describe that exact instant.
    assert snapshot.energy == pytest.approx(99.975)
    assert snapshot.fatigue == pytest.approx(0.015)
    assert snapshot.revision == 1
    assert snapshot.captured_at == datetime.fromtimestamp(105.0, timezone.utc)


def test_advance_to_rejects_time_regression_with_typed_error() -> None:
    # Given: homeostasis already advanced past its initial instant.
    energy = EnergySystem(clock=lambda: 10.0)
    energy.advance_to(15.0)

    # When / Then: an older timestamp is rejected with structured evidence.
    with pytest.raises(EnergyTimeRegressionError) as captured:
        energy.advance_to(14.0)
    assert captured.value.previous_timestamp == 15.0
    assert captured.value.requested_timestamp == 14.0


def test_homeostasis_snapshot_is_immutable() -> None:
    # Given: a sealed homeostasis snapshot.
    snapshot = EnergySystem(clock=lambda: 0.0).snapshot(0.0)

    # When / Then: callers cannot write state back through the snapshot.
    with pytest.raises(ValidationError):
        snapshot.energy = 0.0
