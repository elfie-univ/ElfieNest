"""Acceptance checks for the reviewed old-age mortality curve."""

from __future__ import annotations

import pytest

from elfie.genesis.family import _sample_conditioned_death_age


def sample(uniform: float, survival: int = 0) -> int:
    return _sample_conditioned_death_age(
        elder_start_age=10,
        median_age=15,
        terminal_age=17,
        minimum_survival_age=survival,
        early_cdf_power=4,
        late_survival_power=2,
        uniform=uniform,
    )


def test_reviewed_age_table_and_increasing_annual_mortality() -> None:
    ages = [sample((i + 0.5) / 10_000) for i in range(10_000)]
    expected = {
        10: 0,
        11: 0.0008,
        12: 0.0128,
        13: 0.0648,
        14: 0.2048,
        15: 0.5,
        16: 0.875,
        17: 1,
    }
    previous = 0.0
    hazards = []
    for age, cumulative in expected.items():
        actual = sum(a <= age for a in ages) / len(ages)
        assert actual == pytest.approx(cumulative, abs=0.0001)
        if age > 10:
            hazards.append((actual - previous) / (1 - previous))
        previous = actual
    assert hazards == sorted(hazards)
    assert min(ages) == 11
    assert max(ages) == 17


@pytest.mark.parametrize("survival", [0, 6, 10, 12, 15, 16])
def test_conditioning_preserves_required_survival_and_remaining_distribution(
    survival: int,
) -> None:
    ages = [sample((i + 0.5) / 10_000, survival) for i in range(10_000)]
    cdf = {0: 0, 6: 0, 10: 0, 12: 0.0128, 15: 0.5, 16: 0.875}
    assert min(ages) > max(10, survival)
    assert max(ages) <= 17
    expected = max(0, (0.5 - cdf[survival]) / (1 - cdf[survival]))
    assert sum(a <= 15 for a in ages) / len(ages) == pytest.approx(expected, abs=0.0001)


@pytest.mark.parametrize("uniform", [0, 1, float("nan")])
def test_invalid_draws_are_rejected(uniform: float) -> None:
    with pytest.raises(ValueError):
        sample(uniform)


def test_terminal_age_cannot_be_a_survival_anchor() -> None:
    with pytest.raises(ValueError):
        sample(0.5, 17)
