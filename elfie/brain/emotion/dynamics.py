"""Deterministic growth, direct inhibition, and passive recovery equations."""

from __future__ import annotations

import math
from collections.abc import Iterable


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def noisy_or(values: Iterable[float]) -> float:
    """Combine same-window evidence without diluting a strong observation."""

    result = 0.0
    for value in values:
        result = 1.0 - (1.0 - result) * (1.0 - _clamp(value))
    return _clamp(result)


def passive_return(
    current: float,
    baseline: float,
    dt: float,
    half_life_seconds: float,
) -> float:
    """Move toward baseline with an exponential half-life."""

    if dt < 0:
        raise ValueError("dt must be non-negative")
    if half_life_seconds <= 0:
        raise ValueError("half_life_seconds must be positive")
    if dt == 0:
        return _clamp(current)
    factor = math.pow(2.0, -dt / half_life_seconds)
    return _clamp(baseline + (current - baseline) * factor)


def apply_signed_drive(
    *,
    current: float,
    baseline: float,
    positive_gain: float,
    negative_gain: float,
    positive_evidence: float,
    negative_evidence: float,
    dose: float = 1.0,
) -> float:
    """Apply one discrete event's signed drive to one channel.

    Positive drive saturates toward 1. Negative drive consumes the current
    stock directly. Equal calibrated drives cancel, leaving the passive
    trajectory untouched. ``dose`` is an event dose, never wall-clock time.
    """

    if positive_gain < 0 or negative_gain < 0:
        raise ValueError("gains must be non-negative")
    if dose < 0:
        raise ValueError("dose must be non-negative")
    p = positive_gain * _clamp(positive_evidence)
    n = negative_gain * _clamp(negative_evidence)
    drive = p - n
    value = _clamp(current)
    _ = _clamp(baseline)  # validate the configured baseline input
    if dose == 0 or drive == 0:
        return value
    if drive > 0:
        return _clamp(1.0 - (1.0 - value) * math.exp(-drive * dose))
    return _clamp(value * math.exp(drive * dose))


def calibrate_strength(
    strength: int | float,
    *,
    knots: tuple[float, ...] = (0.0, 0.12, 0.28, 0.55, 0.85, 1.0),
) -> float:
    """Map semantic 0..100 strength to a bounded nonlinear dose fraction."""

    if not 0 <= float(strength) <= 100:
        raise ValueError("strength must be between 0 and 100")
    if len(knots) < 2 or any(not 0 <= item <= 1 for item in knots):
        raise ValueError("strength knots must be bounded")
    position = float(strength) / 100.0 * (len(knots) - 1)
    lower = min(len(knots) - 2, int(position))
    fraction = position - lower
    return _clamp(knots[lower] + (knots[lower + 1] - knots[lower]) * fraction)


__all__ = ("apply_signed_drive", "calibrate_strength", "noisy_or", "passive_return")
