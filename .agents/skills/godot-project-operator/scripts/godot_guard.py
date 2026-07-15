#!/usr/bin/env python3
"""Inspect and launch one Godot instance without silently duplicating it."""

from __future__ import annotations

import argparse
import csv
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROJECT = REPO_ROOT / "godot"
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
        description="Safely inspect, validate, or launch one Godot project instance."
    )
    parser.add_argument(
        "command", choices=("doctor", "status", "editor", "run", "validate")
    )
    parser.add_argument(
        "--project", type=Path, default=DEFAULT_PROJECT, help="Godot project directory"
    )
    parser.add_argument("--godot", type=Path, help="Godot executable path")
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Allow launch with a different Godot major.minor version",
    )
    parser.add_argument(
        "--script", default=DEFAULT_VALIDATION_SCRIPT, help="Validation GDScript"
    )
    return parser.parse_args()


def find_godot(explicit: Path | None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit.expanduser())
    if os.environ.get("GODOT_BIN"):
        candidates.append(Path(os.environ["GODOT_BIN"]).expanduser())

    for name in ("godot4", "godot", "Godot", "godot4.exe", "godot.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    if platform.system() == "Darwin":
        candidates.extend(
            [
                Path("/Applications/Godot.app/Contents/MacOS/Godot"),
                Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
                Path.home() / "Downloads/Godot.app/Contents/MacOS/Godot",
            ]
        )

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def project_version(project: Path) -> str | None:
    project_file = project / "project.godot"
    if not project_file.is_file():
        return None
    match = re.search(
        r'config/features=PackedStringArray\("(\d+\.\d+)"',
        project_file.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def installed_version(binary: Path) -> str | None:
    result = subprocess.run(
        [str(binary), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    match = re.search(r"(\d+\.\d+)", result.stdout + result.stderr)
    return match.group(1) if match else None


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


def print_processes(processes: list[GodotProcess], project: Path) -> None:
    if not processes:
        print("Godot processes: none")
        return

    project_text = str(project.resolve())
    print(f"Godot processes: {len(processes)}")
    for process in processes:
        memory = "unknown"
        if process.rss_kib is not None:
            memory = f"{process.rss_kib / 1024:.1f} MiB RSS"
        ownership = (
            "this project" if project_text in process.command else "unknown project"
        )
        print(f"  PID {process.pid}: {memory}, {ownership}")
        print(f"    {process.command}")


def check_environment(
    project: Path, binary: Path | None, allow_mismatch: bool
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
    actual = installed_version(binary)
    if expected and actual and expected != actual and not allow_mismatch:
        print(
            f"ERROR: project requires Godot {expected}, but executable is {actual}. "
            "Use a matching engine. Pass --allow-version-mismatch only after user approval.",
            file=sys.stderr,
        )
        return False, expected, actual
    return True, expected, actual


def launch(
    binary: Path, project: Path, editor: bool, processes: list[GodotProcess]
) -> int:
    if processes:
        print_processes(processes, project)
        print(
            "REFUSED: reuse the existing Godot window; no duplicate instance was started.",
            file=sys.stderr,
        )
        return 3

    command = [str(binary)]
    if editor:
        command.append("--editor")
    command.extend(["--path", str(project)])

    popen_options: dict[str, object] = {
        "cwd": str(project),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_options["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        popen_options["start_new_session"] = True

    process = subprocess.Popen(command, **popen_options)
    mode = "editor" if editor else "game"
    print(f"Started one Godot {mode} instance (PID {process.pid}).")
    print("Do not run another launch command while this process exists.")
    return 0


def validate(
    binary: Path, project: Path, script: str, processes: list[GodotProcess]
) -> int:
    if processes:
        print_processes(processes, project)
        print(
            "REFUSED: close or reuse the existing Godot instance before headless validation.",
            file=sys.stderr,
        )
        return 3

    command = [
        str(binary),
        "--headless",
        "--path",
        str(project),
        "--script",
        script,
    ]
    print("Running one synchronous headless validation process...")
    result = subprocess.run(command, cwd=project, check=False)
    print("Headless validation process exited.")
    return result.returncode


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
        project, binary, args.allow_version_mismatch
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
    if args.command == "editor":
        return launch(binary, project, editor=True, processes=processes)
    if args.command == "run":
        return launch(binary, project, editor=False, processes=processes)
    return validate(binary, project, args.script, processes=processes)


if __name__ == "__main__":
    raise SystemExit(main())
