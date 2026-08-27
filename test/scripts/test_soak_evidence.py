from __future__ import annotations

import pytest

from scripts.internal.release.soak_evidence import (
    SoakBudget,
    SoakEvidenceError,
    SoakSample,
    classify_soak,
)


def _sample(
    generation: int, rss: int, *, cpu: float = 10.0, errors: int = 0
) -> SoakSample:
    return SoakSample("", generation, (100, 101), cpu, rss, errors, 0)


def test_soak_classifier_reports_stable_generation_and_resource_trend() -> None:
    result = classify_soak(
        [_sample(4, 100), _sample(4, 105), _sample(4, 110)], warmup_samples=1
    )

    assert result["result"] == "passed"
    assert result["generation_changes"] == 0
    assert result["rss_growth_ratio"] == pytest.approx(0.047619, abs=1e-6)


def test_soak_classifier_fails_on_unexplained_error_and_memory_growth() -> None:
    with pytest.raises(SoakEvidenceError, match="rss_growth,error_growth"):
        classify_soak(
            [_sample(4, 100), _sample(4, 130, errors=1)],
            budget=SoakBudget(
                max_error_delta=0,
                max_rss_growth_ratio=0.15,
            ),
            warmup_samples=0,
        )


def test_soak_classifier_allows_one_predeclared_generation_change() -> None:
    result = classify_soak([_sample(4, 100), _sample(5, 105)], warmup_samples=0)
    assert result["result"] == "passed"
    assert result["generation_changes"] == 1
