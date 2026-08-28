"""Cluster-aware effect estimates for repeated trajectory comparisons."""

from __future__ import annotations

import random
from collections import defaultdict
from statistics import fmean
from typing import DefaultDict, Iterable, List

from devtools.brain_eval.contracts import (
    DimensionEffect,
    PairwiseOutcome,
    QualityDimension,
)


def estimate_dimension_effect(
    outcomes: Iterable[PairwiseOutcome],
    dimension: QualityDimension,
    *,
    bootstrap_samples: int = 2000,
    confidence_level: float = 0.95,
    random_seed: int = 0,
) -> DimensionEffect:
    """Estimate net win advantage, resampling complete scenario families."""

    if bootstrap_samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    if not 0.5 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0.5 and 1.0")

    selected = [item for item in outcomes if item.dimension is dimension]
    valid = [item for item in selected if item.valid and item.value is not None]
    clusters: DefaultDict[str, List[int]] = defaultdict(list)
    for item in valid:
        clusters[item.scenario_family_id].append(item.value)  # type: ignore[arg-type]

    if len(clusters) < 2:
        return DimensionEffect(
            dimension=dimension,
            valid=False,
            pair_count=len(valid),
            invalid_pair_count=len(selected) - len(valid),
            scenario_family_count=len(clusters),
        )

    family_ids = sorted(clusters)
    family_means = {
        family_id: float(fmean(clusters[family_id])) for family_id in family_ids
    }
    estimate = float(fmean(family_means.values()))
    generator = random.Random(random_seed)
    samples: List[float] = []
    for _ in range(bootstrap_samples):
        samples.append(
            float(
                fmean(
                    family_means[generator.choice(family_ids)]
                    for _family_index in family_ids
                )
            )
        )
    samples.sort()
    tail = (1.0 - confidence_level) / 2.0
    lower = _quantile(samples, tail)
    upper = _quantile(samples, 1.0 - tail)
    return DimensionEffect(
        dimension=dimension,
        valid=True,
        net_advantage=estimate,
        lower_bound=lower,
        upper_bound=upper,
        pair_count=len(valid),
        invalid_pair_count=len(selected) - len(valid),
        scenario_family_count=len(clusters),
    )


def _quantile(values: List[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


__all__ = ("estimate_dimension_effect",)
