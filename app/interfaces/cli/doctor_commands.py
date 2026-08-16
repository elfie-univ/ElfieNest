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


def find_all_elfienest_processes(
    lifecycle: LifecycleFacade,
) -> Tuple[ProcessInfo, ...]:
    """
    Find all ElfieNest background service processes.

    Only includes:
    - Core service processes identified by the lifecycle boundary
    - Electron processes running godot-authority role
    - Electron helper processes spawned by godot-authority
    """
    processes: list[ProcessInfo] = []
    current_pid = lifecycle.current_pid()
    godot_authority_pids: set[int] = set()

    try:
        entries = lifecycle.list_processes()

        # First pass: identify main processes
        for entry in entries:
            pid = entry.pid
            command = " ".join(entry.command)

            if pid == current_pid:
                continue

            is_elfienest = False
            process_type = "other"

            # Managed Core service process
            if lifecycle.is_managed_service_command(entry.command):
                is_elfienest = True
                process_type = "python"
            # Electron godot-authority process
            elif "--elfienest-role=godot-authority" in command:
                is_elfienest = True
                process_type = "electron"
                godot_authority_pids.add(pid)

            if is_elfienest:
                processes.append(
                    ProcessInfo(
                        pid=pid,
                        command=entry.command,
                        cwd=entry.cwd,
                        process_type=process_type,
                    )
                )

        # Second pass: find Electron helper processes
        if godot_authority_pids:
            for entry in entries:
                pid = entry.pid
                ppid = entry.parent_pid
                command = " ".join(entry.command)

                if pid == current_pid or any(p.pid == pid for p in processes):
                    continue

                if ppid in godot_authority_pids and "Electron" in command:
                    processes.append(
                        ProcessInfo(
                            pid=pid,
                            command=entry.command,
                            cwd=entry.cwd,
                            process_type="electron",
                        )
                    )

    except (OSError, RuntimeError, TimeoutError):
        pass

    return tuple(processes)


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


def interactive_port_cleanup(
    lifecycle: LifecycleFacade,
    ports: Tuple[int, ...] = DEFAULT_SERVICE_PORTS,
    *,
    force: bool = False,
) -> bool:
    """Diagnose occupied ports without terminating an unverified process.

    Port ownership is evidence only.  A Doctor command does not have the
    current Runtime generation's authenticated process lease, so it must not
    turn a port lookup into a kill operation.  The lifecycle start/stop
    commands already have the exact data-root and process identity required to
    stop a managed service safely.
    """
    _ = force
    occupied_ports = diagnose_ports(lifecycle, ports)
    if not occupied_ports:
        print("  ✅ No ElfieNest processes or occupied ports found")
        return True

    print()
    print("  ⚠️  Port occupation detected (diagnostic only):")
    for port, proc_info in occupied_ports.items():
        print(f"  - Port {port}: PID {proc_info.pid}")
        if proc_info.command:
            print(f"    Command: {_compact_command(proc_info.command)}")
        if proc_info.cwd:
            print(f"    Working directory: {proc_info.cwd}")
    print()
    print("  ℹ️  Doctor will not terminate a process from a port lookup.")
    print("     Stop the exact ElfieNest data root with 'elfienest stop',")
    print("     or start with an explicit unused port.")
    return False


def _compact_command(command: Tuple[str, ...]) -> str:
    """Keep a diagnostic command line readable without changing its evidence."""
    value = " ".join(command)
    return value if len(value) <= 120 else value[:117] + "..."


def run_doctor_with_port_fix(
    lifecycle: LifecycleFacade,
    fix_ports: bool = False,
    force: bool = False,
) -> int:
    """Run doctor with an explicitly non-destructive port diagnostic."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()

    # Port diagnostics first
    if fix_ports:
        interactive_port_cleanup(lifecycle, force=force)
        print()

    # Original doctor repairs
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
