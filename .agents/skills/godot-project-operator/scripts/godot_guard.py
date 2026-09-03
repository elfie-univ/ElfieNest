#!/usr/bin/env python3
"""Inspect and validate one Godot project without silently duplicating it."""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from infrastructure.godot import runner as godot_runner  # noqa: E402

DEFAULT_PROJECT = REPO_ROOT / "godot_project"
DEFAULT_VALIDATION_SCRIPT = "res://scripts/test/test_scene_resource_contract.gd"


@dataclass(frozen=True)
class GodotProcess:
    pid: int
    rss_kib: int | None
    command: str


class ProcessInspectionError(RuntimeError):
    """Raised when process ownership cannot be checked safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely inspect or validate one Godot project instance."
    )
    parser.add_argument("command", choices=("doctor", "status", "prepare", "validate"))
    parser.add_argument(
        "--project", type=Path, default=DEFAULT_PROJECT, help="Godot project directory"
    )
    parser.add_argument("--godot", type=Path, help="Godot executable path")
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Allow validation with a different Godot major.minor version",
    )
    parser.add_argument(
        "--script", default=DEFAULT_VALIDATION_SCRIPT, help="Validation GDScript"
    )
    return parser.parse_args()


def find_godot(explicit: Path | None) -> Path | None:
    return godot_runner.find_godot(explicit)


def project_version(project: Path) -> str | None:
    return godot_runner.project_version(project)


def installed_version(binary: Path) -> str | None:
    return godot_runner.godot_version(binary)


def godot_processes() -> list[GodotProcess]:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise ProcessInspectionError(f"could not run tasklist: {error}") from error
        if result.returncode != 0:
            raise ProcessInspectionError(result.stderr.strip() or "tasklist failed")
        processes = []
        for fields in csv.reader(result.stdout.splitlines()):
            if len(fields) < 2 or not fields[0].lower().startswith("godot"):
                continue
            if fields[1].isdigit():
                processes.append(GodotProcess(int(fields[1]), None, fields[0]))
        return processes

    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,rss=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ProcessInspectionError(f"could not run ps: {error}") from error
    if result.returncode != 0:
        raise ProcessInspectionError(result.stderr.strip() or "ps failed")
    processes = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) != 3:
            continue
        if not fields[0].isdigit() or not fields[1].isdigit():
            continue
        try:
            executable = Path(shlex.split(fields[2])[0]).name.lower()
        except (ValueError, IndexError):
            continue
        if not executable.startswith("godot"):
            continue
        processes.append(GodotProcess(int(fields[0]), int(fields[1]), fields[2]))
    return processes


def process_project_path(command: str) -> Path | None:
    """Extract an absolute project path from a Godot command line."""
    try:
        arguments = shlex.split(command)
    except ValueError:
        return None
    for index, argument in enumerate(arguments):
        if argument == "--path":
            if index + 1 >= len(arguments):
                return None
            raw_path = arguments[index + 1]
        elif argument.startswith("--path="):
            raw_path = argument.split("=", maxsplit=1)[1]
        else:
            continue
        project_path = Path(raw_path).expanduser()
        if not project_path.is_absolute():
            return None
        return project_path.resolve()
    return None


def blocking_processes(
    processes: list[GodotProcess], project: Path
) -> list[GodotProcess]:
    """Return same-project or unidentifiable Godot processes.

    A known different project has an independent import cache and does not
    prevent this project's headless validation from starting. An
    unidentifiable command remains blocking so the guard never guesses that
    two processes are isolated when it cannot prove it.
    """
    target = project.resolve()
    blocking: list[GodotProcess] = []
    for process in processes:
        process_project = process_project_path(process.command)
        if process_project is None or process_project == target:
            blocking.append(process)
    return blocking


def print_processes(processes: list[GodotProcess], project: Path) -> None:
    if not processes:
        print("Godot processes: none")
        return

    target = project.resolve()
    print(f"Godot processes: {len(processes)}")
    for process in processes:
        memory = "unknown"
        if process.rss_kib is not None:
            memory = f"{process.rss_kib / 1024:.1f} MiB RSS"
        process_project = process_project_path(process.command)
        if process_project == target:
            ownership = "this project"
        elif process_project is None:
            ownership = "unknown project"
        else:
            ownership = "other project"
        print(f"  PID {process.pid}: {memory}, {ownership}")
        print(f"    {process.command}")


def check_environment(
    project: Path,
    binary: Path | None,
    allow_mismatch: bool,
    *,
    probe_version: bool = True,
) -> tuple[bool, str | None, str | None]:
    project_file = project / "project.godot"
    if not project_file.is_file():
        print(f"ERROR: project.godot not found under {project}", file=sys.stderr)
        return False, None, None
    if binary is None:
        print(
            "ERROR: Godot executable not found; pass --godot or set GODOT_BIN.",
            file=sys.stderr,
        )
        return False, None, None

    expected = project_version(project)
    # ``validate`` must have exactly one Godot process.  It gets the actual
    # version from that headless process's startup output instead of probing
    # ``--version`` first.  ``doctor`` still performs the standalone probe.
    actual = installed_version(binary) if probe_version else None
    if expected and actual and expected != actual and not allow_mismatch:
        print(
            f"ERROR: project requires Godot {expected}, but executable is {actual}. "
            "Use a matching engine. Pass --allow-version-mismatch only after user approval.",
            file=sys.stderr,
        )
        return False, expected, actual
    return True, expected, actual


def _import_destinations(import_file: Path) -> list[Path]:
    try:
        contents = import_file.read_text(encoding="utf-8")
    except OSError:
        return []
    marker = "dest_files=["
    marker_start = contents.find(marker)
    if marker_start < 0:
        return []
    values_start = marker_start + len(marker)
    values_end = contents.find("]", values_start)
    if values_end < 0:
        return []
    destinations: list[Path] = []
    for raw_value in contents[values_start:values_end].split(","):
        destination = raw_value.strip().strip('"')
        if destination.startswith("res://"):
            destinations.append(Path(destination.removeprefix("res://")))
    return destinations


def project_import_ready(project: Path) -> bool:
    """Return whether Godot's generated class and asset caches are usable."""

    resolved_project = project.expanduser().resolve()
    class_cache = resolved_project / ".godot" / "global_script_class_cache.cfg"
    imported_root = resolved_project / ".godot" / "imported"
    if not class_cache.is_file() or not imported_root.is_dir():
        return False
    try:
        class_cache_text = class_cache.read_text(encoding="utf-8")
        class_cache_mtime = class_cache.stat().st_mtime
    except OSError:
        return False
    for required_class in ("ModularNest", "ElfieActor"):
        if f'"class": &"{required_class}"' not in class_cache_text:
            return False

    for source_path in resolved_project.rglob("*.gd"):
        if ".godot" in source_path.parts:
            continue
        try:
            if source_path.stat().st_mtime > class_cache_mtime:
                return False
        except OSError:
            return False

    found_import_metadata = False
    for import_file in resolved_project.rglob("*.import"):
        if ".godot" in import_file.parts:
            continue
        found_import_metadata = True
        destinations = _import_destinations(import_file)
        if not destinations:
            continue
        for destination in destinations:
            generated = resolved_project / destination
            if not generated.is_file():
                return False
    return found_import_metadata


def prepare_import(
    binary: Path,
    project: Path,
    processes: list[GodotProcess],
    expected_version: str | None,
    allow_version_mismatch: bool,
) -> int:
    """Generate Godot's ignored first-run caches when they are absent/stale."""

    if project_import_ready(project):
        print("Godot project import cache is ready; skipping import preflight.")
        return 0
    conflicts = blocking_processes(processes, project)
    if conflicts:
        print_processes(conflicts, project)
        print(
            "REFUSED: close or reuse the existing instance for this project, or identify the unknown process, before Godot import.",
            file=sys.stderr,
        )
        return 3

    print("Running one synchronous headless Godot project import preflight...")
    result = godot_runner.run_import(
        binary,
        project,
        godot_version=None,
        purpose="guard-project-import",
    )
    godot_runner.forward_output(result)
    if result.exit_code != 0:
        print(
            f"Godot project import process failed with exit code {result.exit_code}.",
            file=sys.stderr,
        )
        return result.exit_code
    if (
        expected_version
        and result.godot_version
        and expected_version != result.godot_version
        and not allow_version_mismatch
    ):
        print(
            f"ERROR: project requires Godot {expected_version}, but import used "
            f"{result.godot_version}.",
            file=sys.stderr,
        )
        return 2
    if not project_import_ready(project):
        print(
            "ERROR: Godot import exited successfully but did not produce a ready class/resource cache.",
            file=sys.stderr,
        )
        return 1
    print("Godot project import preflight exited with a ready cache.")
    return 0


def validate(
    binary: Path,
    project: Path,
    script: str,
    processes: list[GodotProcess],
    expected_version: str | None,
    allow_version_mismatch: bool,
) -> int:
    if not project_import_ready(project):
        import_exit = prepare_import(
            binary,
            project,
            processes,
            expected_version=expected_version,
            allow_version_mismatch=allow_version_mismatch,
        )
        if import_exit != 0:
            return import_exit
        try:
            processes = godot_processes()
        except ProcessInspectionError as error:
            print(
                f"ERROR: cannot inspect Godot processes safely: {error}",
                file=sys.stderr,
            )
            print("REFUSED: no validation command was run.", file=sys.stderr)
            return 4
    conflicts = blocking_processes(processes, project)
    if conflicts:
        print_processes(conflicts, project)
        print(
            "REFUSED: close or reuse the existing instance for this project, or identify the unknown process, before headless validation.",
            file=sys.stderr,
        )
        return 3

    print("Running one synchronous headless validation process...")
    result = godot_runner.run_headless(
        binary,
        project,
        ("--script", script),
        godot_version=None,
        purpose="guard-validation",
    )
    godot_runner.forward_output(result)
    if result.exit_code != 0:
        print(
            f"Headless validation process failed with exit code {result.exit_code}.",
            file=sys.stderr,
        )
        return result.exit_code

    actual_version = result.godot_version
    if (
        expected_version
        and actual_version
        and expected_version != actual_version
        and not allow_version_mismatch
    ):
        print(
            f"ERROR: project requires Godot {expected_version}, but executable is "
            f"{actual_version}. Use a matching engine. Pass "
            "--allow-version-mismatch only after user approval.",
            file=sys.stderr,
        )
        return 2

    print("Headless validation process exited.")
    return result.exit_code


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    binary = find_godot(args.godot)
    try:
        processes = godot_processes()
    except ProcessInspectionError as error:
        print(f"ERROR: cannot inspect Godot processes safely: {error}", file=sys.stderr)
        print("REFUSED: no launch or validation command was run.", file=sys.stderr)
        return 4

    if args.command == "status":
        print_processes(processes, project)
        return 0

    ok, expected, actual = check_environment(
        project,
        binary,
        args.allow_version_mismatch,
        probe_version=args.command == "doctor",
    )
    if args.command == "doctor":
        print(f"Project: {project}")
        print(f"Required Godot: {expected or 'unknown'}")
        print(f"Godot executable: {binary or 'not found'}")
        print(f"Installed Godot: {actual or 'unknown'}")
        print_processes(processes, project)
        return 0 if ok else 2
    if not ok or binary is None:
        return 2
    if args.command == "prepare":
        return prepare_import(
            binary,
            project,
            processes=processes,
            expected_version=expected,
            allow_version_mismatch=args.allow_version_mismatch,
        )
    return validate(
        binary,
        project,
        args.script,
        processes=processes,
        expected_version=expected,
        allow_version_mismatch=args.allow_version_mismatch,
    )


if __name__ == "__main__":
    raise SystemExit(main())
