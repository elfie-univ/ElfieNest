"""Local doctor diagnostics and safe auto-repair entry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.orchestration.lifecycle import (
    DEFAULT_SERVICE_PORTS,
    DoctorRepairResult,
    LifecycleFacade,
)


def run_doctor(lifecycle: LifecycleFacade) -> int:
    """Run safe local repairs first, then offline runtime and config checks."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()
    try:
        repairs = repair_local_runtime_state(lifecycle)
        if repairs.repaired:
            print("  🔧 Auto-repaired:")
            for item in repairs.repaired:
                print(f"    - {item}")
            print()
        else:
            print("  ✅ Local structure needs no repair")
            print()
        report = lifecycle.run_offline_validation()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"  ❌ Doctor failed: {error}")
        return 1
    print(
        "  ✅ Repair and diagnostics complete"
        if report.passed
        else "  ⚠️  Repair complete, diagnostics found issues"
    )
    return 0 if report.passed else 1


def repair_local_runtime_state(lifecycle: LifecycleFacade) -> DoctorRepairResult:
    """Repair local state that needs no network, keys, or user data deletion."""
    return lifecycle.repair_local_state()


@dataclass(frozen=True)
class ProcessInfo:
    """Information about a running process."""

    pid: int
    command: Tuple[str, ...]
    cwd: Optional[Path]
    process_type: str  # "python", "electron", "other"


def diagnose_ports(
    lifecycle: LifecycleFacade,
    ports: Tuple[int, ...] = DEFAULT_SERVICE_PORTS,
) -> dict[int, ProcessInfo]:
    """
    Diagnose port occupation.

    Returns:
        Dict mapping port -> ProcessInfo (or None if not occupied)
    """
    occupied: dict[int, ProcessInfo] = {}

    for port in ports:
        pid = lifecycle.port_occupant_pid(port)
        if pid:
            try:
                # Get process details
                snapshot = lifecycle.inspect_process(pid)
                command = snapshot.command
                cwd = snapshot.cwd if lifecycle.process_exists(pid) else None

                occupied[port] = ProcessInfo(
                    pid=pid,
                    command=command,
                    cwd=cwd,
                    process_type="unknown",
                )
            except (OSError, RuntimeError):
                # If we can't get details, just record the PID
                occupied[port] = ProcessInfo(
                    pid=pid,
                    command=(),
                    cwd=None,
                    process_type="unknown",
                )

    return occupied
