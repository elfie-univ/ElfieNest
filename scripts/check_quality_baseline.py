"""Check current Python quality diagnostics against a tracked debt baseline."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, TypeAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_PATH = PROJECT_ROOT / ".quality-baseline.json"
MYPY_SOURCE_ROOTS: Tuple[str, ...] = (
    "ai_runtime",
    "app",
    "elfie",
    "nest",
    "devtools",
    "scripts",
)
RUFF_CHECK_COMMAND = ("ruff", "check", "--output-format", "json", ".")
RUFF_FORMAT_COMMAND = ("ruff", "format", "--check", ".")
MYPY_COMMAND = ("mypy", "-O", "json", *MYPY_SOURCE_ROOTS)


class RuffLocation(BaseModel):
    """Location emitted by Ruff's JSON output."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    row: int
    column: int


class RuffDiagnostic(BaseModel):
    """Validated Ruff JSON diagnostic."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    code: str
    filename: str
    location: RuffLocation
    message: str


class MypyDiagnostic(BaseModel):
    """Validated MyPy JSON diagnostic."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    file: str
    line: int
    column: int
    message: str
    code: Optional[str]
    severity: str


class QualityBaseline(BaseModel):
    """Tracked diagnostic counters for every Python quality gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    ruff_check: Dict[str, int]
    ruff_format: Dict[str, int]
    mypy: Dict[str, int]


RUFF_DIAGNOSTICS = TypeAdapter(List[RuffDiagnostic])


@dataclass(frozen=True)
class QualityToolExecutionError(RuntimeError):
    """A quality tool exited without producing comparable diagnostics."""

    tool: str
    exit_code: int

    def __str__(self) -> str:
        return f"{self.tool} failed to execute (exit {self.exit_code})"


@dataclass(frozen=True)
class DiagnosticDelta:
    """New and resolved diagnostic identities for one quality gate."""

    new: Counter[str]
    resolved: Counter[str]


def parse_ruff_output(output: str, project_root: Path) -> Counter[str]:
    diagnostics = RUFF_DIAGNOSTICS.validate_json(output)
    return Counter(
        _diagnostic_identity(
            _relative_path(diagnostic.filename, project_root),
            diagnostic.code,
            diagnostic.message,
        )
        for diagnostic in diagnostics
    )


def parse_mypy_output(output: str, project_root: Path) -> Counter[str]:
    diagnostics = (
        MypyDiagnostic.model_validate_json(line)
        for line in output.splitlines()
        if line.strip()
    )
    return Counter(
        _diagnostic_identity(
            _relative_path(diagnostic.file, project_root),
            diagnostic.code or "no-code",
            diagnostic.message,
        )
        for diagnostic in diagnostics
    )


def parse_ruff_format_output(output: str, project_root: Path) -> Counter[str]:
    paths = (
        line.removeprefix("Would reformat: ").strip()
        for line in output.splitlines()
        if line.startswith("Would reformat: ")
    )
    return Counter(_format_identity(path, project_root) for path in paths)


def compare_diagnostics(
    baseline: Counter[str], current: Counter[str]
) -> DiagnosticDelta:
    return DiagnosticDelta(new=current - baseline, resolved=baseline - current)


def quality_exit_code(deltas: Mapping[str, DiagnosticDelta]) -> int:
    return int(any(delta.new for delta in deltas.values()))


def format_gate_summary(deltas: Mapping[str, DiagnosticDelta]) -> str:
    lines = [
        f"{gate}: new={sum(delta.new.values())}, "
        f"resolved={sum(delta.resolved.values())}"
        for gate, delta in sorted(deltas.items())
    ]
    return "\n".join(lines)


def _diagnostic_identity(path: str, code: str, message: str) -> str:
    message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    return f"{path}:{code}:{message_hash}"


def _format_identity(path: str, project_root: Path) -> str:
    relative_path = _relative_path(path, project_root)
    content_hash = hashlib.sha256(
        (project_root / relative_path).read_bytes()
    ).hexdigest()
    return f"{relative_path}:format:{content_hash}"


def _relative_path(path: str, project_root: Path) -> str:
    candidate = Path(path)
    absolute_path = candidate if candidate.is_absolute() else project_root / candidate
    return absolute_path.resolve().relative_to(project_root.resolve()).as_posix()


def _run_command(
    command: Sequence[str], project_root: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )


def collect_current_diagnostics(project_root: Path) -> Dict[str, Counter[str]]:
    """Run every quality tool and return sanitized diagnostic counters."""
    ruff_check = _run_command(RUFF_CHECK_COMMAND, project_root)
    ruff_format = _run_command(RUFF_FORMAT_COMMAND, project_root)
    mypy = _run_command(MYPY_COMMAND, project_root)
    for name, result in (
        ("ruff_check", ruff_check),
        ("ruff_format", ruff_format),
        ("mypy", mypy),
    ):
        if result.returncode not in (0, 1):
            raise QualityToolExecutionError(name, result.returncode)
    return {
        "ruff_check": parse_ruff_output(ruff_check.stdout, project_root),
        "ruff_format": parse_ruff_format_output(
            ruff_format.stdout + ruff_format.stderr, project_root
        ),
        "mypy": parse_mypy_output(mypy.stdout, project_root),
    }


def _baseline_counters(baseline: QualityBaseline) -> Dict[str, Counter[str]]:
    return {
        "ruff_check": Counter(baseline.ruff_check),
        "ruff_format": Counter(baseline.ruff_format),
        "mypy": Counter(baseline.mypy),
    }


def _build_baseline(current: Mapping[str, Counter[str]]) -> QualityBaseline:
    return QualityBaseline(
        schema_version=1,
        ruff_check=dict(sorted(current["ruff_check"].items())),
        ruff_format=dict(sorted(current["ruff_format"].items())),
        mypy=dict(sorted(current["mypy"].items())),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the baseline gate or explicitly refresh its tracked snapshot."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true")
    arguments = parser.parse_args(argv)
    current = collect_current_diagnostics(PROJECT_ROOT)
    if arguments.write_baseline:
        baseline = _build_baseline(current)
        arguments.baseline.write_text(
            baseline.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print("quality baseline written")
        return 0
    baseline = QualityBaseline.model_validate_json(
        arguments.baseline.read_text(encoding="utf-8")
    )
    expected = _baseline_counters(baseline)
    deltas = {
        gate: compare_diagnostics(expected[gate], diagnostics)
        for gate, diagnostics in current.items()
    }
    print(format_gate_summary(deltas))
    return quality_exit_code(deltas)


if __name__ == "__main__":
    sys.exit(main())
