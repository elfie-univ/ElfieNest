#!/usr/bin/env python3
"""Classify bounded native-soak samples without controlling any process."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class SoakEvidenceError(ValueError):
    """Raised when a sample stream is malformed or breaches a frozen budget."""


@dataclass(frozen=True)
class SoakSample:
    timestamp: str
    generation: int
    pids: tuple[int, ...]
    cpu_percent: float | None
    rss_bytes: int | None
    error_count: int
    fatal_count: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SoakSample:
        generation = payload.get("generation")
        pids = payload.get("pids", [])
        if not isinstance(generation, int) or generation < 0:
            raise SoakEvidenceError("soak-generation-invalid")
        if not isinstance(pids, list) or any(
            not isinstance(pid, int) or pid <= 0 for pid in pids
        ):
            raise SoakEvidenceError("soak-pids-invalid")
        cpu = payload.get("cpu_percent")
        rss = payload.get("rss_bytes")
        if cpu is not None and (
            not isinstance(cpu, (int, float)) or not math.isfinite(float(cpu))
        ):
            raise SoakEvidenceError("soak-cpu-invalid")
        if rss is not None and (not isinstance(rss, int) or rss < 0):
            raise SoakEvidenceError("soak-rss-invalid")
        errors = payload.get("error_count", 0)
        fatals = payload.get("fatal_count", 0)
        if (
            not isinstance(errors, int)
            or errors < 0
            or not isinstance(fatals, int)
            or fatals < 0
        ):
            raise SoakEvidenceError("soak-error-count-invalid")
        return cls(
            timestamp=str(payload.get("timestamp") or ""),
            generation=generation,
            pids=tuple(sorted(set(pids))),
            cpu_percent=None if cpu is None else float(cpu),
            rss_bytes=rss,
            error_count=errors,
            fatal_count=fatals,
        )


@dataclass(frozen=True)
class SoakBudget:
    max_generation_changes: int = 1
    max_cpu_p95_percent: float = 100.0
    max_rss_growth_ratio: float = 0.15
    max_error_delta: int = 0
    max_fatal_delta: int = 0


def classify_soak(
    samples: Sequence[SoakSample],
    *,
    budget: SoakBudget | None = None,
    warmup_samples: int = 1,
) -> dict[str, Any]:
    """Return redacted trend evidence and fail on a budget breach."""
    budget = budget or SoakBudget()
    if not samples:
        raise SoakEvidenceError("soak-samples-empty")
    if warmup_samples < 0 or warmup_samples >= len(samples):
        raise SoakEvidenceError("soak-warmup-invalid")
    generations = [sample.generation for sample in samples]
    changes = sum(left != right for left, right in zip(generations, generations[1:]))
    cpu_values = [
        sample.cpu_percent
        for sample in samples[warmup_samples:]
        if sample.cpu_percent is not None
    ]
    rss_values = [
        sample.rss_bytes
        for sample in samples[warmup_samples:]
        if sample.rss_bytes is not None
    ]
    baseline_rss = rss_values[0] if rss_values else None
    peak_rss = max(rss_values) if rss_values else None
    if baseline_rss is None or baseline_rss == 0 or peak_rss is None:
        rss_growth_ratio = 0.0
    else:
        rss_growth_ratio = max(0.0, (peak_rss - baseline_rss) / baseline_rss)
    cpu_p95 = _percentile(cpu_values, 95.0)
    error_delta = max(0, samples[-1].error_count - samples[0].error_count)
    fatal_delta = max(0, samples[-1].fatal_count - samples[0].fatal_count)
    violations: list[str] = []
    if changes > budget.max_generation_changes:
        violations.append("generation_changes")
    if cpu_p95 is not None and cpu_p95 > budget.max_cpu_p95_percent:
        violations.append("cpu_p95")
    if rss_growth_ratio > budget.max_rss_growth_ratio:
        violations.append("rss_growth")
    if error_delta > budget.max_error_delta:
        violations.append("error_growth")
    if fatal_delta > budget.max_fatal_delta:
        violations.append("fatal_growth")
    result = {
        "schema_version": 1,
        "sample_count": len(samples),
        "generation_changes": changes,
        "generations": sorted(set(generations)),
        "cpu_p95_percent": cpu_p95,
        "baseline_rss_bytes": baseline_rss,
        "peak_rss_bytes": peak_rss,
        "rss_growth_ratio": round(rss_growth_ratio, 6),
        "error_delta": error_delta,
        "fatal_delta": fatal_delta,
        "violations": violations,
        "result": "failed" if violations else "passed",
    }
    if violations:
        raise SoakEvidenceError(
            "soak-budget-breached violations=" + ",".join(violations)
        )
    return result


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def load_samples(path: Path) -> list[SoakSample]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SoakEvidenceError("soak-samples-unreadable") from error
    samples: list[SoakSample] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise SoakEvidenceError("soak-sample-json-invalid") from error
        if not isinstance(payload, dict):
            raise SoakEvidenceError("soak-sample-root-invalid")
        samples.append(SoakSample.from_dict(payload))
    return samples


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-samples", type=int, default=1)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        result = classify_soak(
            load_samples(args.samples), warmup_samples=args.warmup_samples
        )
    except SoakEvidenceError as error:
        print(str(error), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"soak-evidence-passed output={args.output}")
    return 0


__all__ = [
    "SoakBudget",
    "SoakEvidenceError",
    "SoakSample",
    "classify_soak",
    "load_samples",
]


if __name__ == "__main__":
    raise SystemExit(main())
