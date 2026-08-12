"""Local doctor diagnostics and safe auto-repair entry."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set, Tuple

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


def kill_processes_safely(
    lifecycle: LifecycleFacade,
    pids: Set[int],
    timeout_seconds: float = 10.0,
) -> Tuple[Tuple[int, bool, Optional[str]], ...]:
    """Kill a set of processes safely with proper timeout."""
    results: list[Tuple[int, bool, Optional[str]]] = []
    for pid in pids:
        try:
            if not lifecycle.process_exists(pid):
                results.append((pid, True, None))
                continue

            lifecycle.terminate_process(pid)
            results.append((pid, True, None))
        except ProcessLookupError:
            results.append((pid, True, None))
        except PermissionError as error:
            results.append((pid, False, f"Permission denied: {error}"))
        except OSError as error:
            results.append((pid, False, str(error)))

    # Wait for processes to exit
    deadline = time.monotonic() + timeout_seconds
    still_running: Set[int] = {pid for pid, success, _ in results if success}

    while still_running and time.monotonic() < deadline:
        for pid in list(still_running):
            if not lifecycle.process_exists(pid):
                still_running.remove(pid)
        if still_running:
            time.sleep(0.1)

    # Force kill remaining processes
    if still_running:
        for pid in still_running:
            try:
                lifecycle.terminate_process(pid, force=True)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        time.sleep(0.5)

    # Update results
    final_results: list[Tuple[int, bool, Optional[str]]] = []
    for pid, _, error_message in results:
        if error_message:
            final_results.append((pid, False, error_message))
        elif lifecycle.process_exists(pid):
            final_results.append((pid, False, "Process did not exit"))
        else:
            final_results.append((pid, True, None))

    return tuple(final_results)


def cleanup_pid_files(lifecycle: LifecycleFacade) -> Tuple[str, ...]:
    """Clean up stale PID files."""
    cleaned: list[str] = []
    elfie_home = lifecycle.select_data_home(
        None,
        project_root=Path(__file__).resolve().parents[3],
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )
    pid_path = elfie_home / "elfienest.pid"

    if lifecycle.receipt_exists(elfie_home):
        try:
            lifecycle.clear_receipt(elfie_home)
            cleaned.append(f"Removed stale PID file: {pid_path}")
        except OSError as error:
            cleaned.append(f"Failed to remove PID file: {error}")

    return tuple(cleaned)


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
    """Interactively clean up all ElfieNest-related processes and ports."""
    # Step 1: Find all ElfieNest-related processes
    all_processes = find_all_elfienest_processes(lifecycle)

    # Step 2: Check port occupation
    occupied_ports = diagnose_ports(lifecycle, ports)

    has_issues = all_processes or occupied_ports

    if not has_issues:
        print("  ✅ No ElfieNest processes or occupied ports found")
        return True

    # Print detailed diagnostics
    print()
    if all_processes:
        print("  📋 Found ElfieNest-related processes:")
        print()
        for proc in all_processes:
            cmd_str = " ".join(proc.command)
            if len(cmd_str) > 80:
                cmd_str = cmd_str[:77] + "..."
            print(f"  - PID {proc.pid} ({proc.process_type}):")
            print(f"    Command: {cmd_str}")
            if proc.cwd:
                cwd_str = str(proc.cwd)
                if len(cwd_str) > 80:
                    cwd_str = cwd_str[:77] + "..."
                print(f"    Working directory: {cwd_str}")
            print()

    if occupied_ports:
        print("  ⚠️  Port occupation detected:")
        print()
        for port, proc_info in occupied_ports.items():
            print(f"  - Port {port}:")
            print(f"    PID: {proc_info.pid}")
            if proc_info.command:
                cmd_str = " ".join(proc_info.command)
                if len(cmd_str) > 80:
                    cmd_str = cmd_str[:77] + "..."
                print(f"    Command: {cmd_str}")
            if proc_info.cwd:
                cwd_str = str(proc_info.cwd)
                if len(cwd_str) > 80:
                    cwd_str = cwd_str[:77] + "..."
                print(f"    Working directory: {cwd_str}")
            print()

    # Ask for confirmation
    if not force:
        print("  💡 These processes are using service ports or are ElfieNest-related.")
        print("     Killing them will stop any ElfieNest instances or other services.")
        print()
        try:
            response = (
                input("  Kill these processes and clean up? [y/N]: ").strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return False

        if response not in ("y", "yes"):
            print("  Cancelled.")
            return False

    print()
    print("  🔧 Cleaning up ElfieNest processes and ports...")
    print()

    all_success = True

    # Step 3: Kill all ElfieNest processes
    if all_processes:
        pids = {proc.pid for proc in all_processes}
        print(f"  📍 Stopping {len(pids)} ElfieNest process(es)...")
        kill_results = kill_processes_safely(lifecycle, pids, timeout_seconds=10.0)

        for pid, success, error in kill_results:
            if success:
                print(f"  ✅ Stopped PID {pid}")
            else:
                all_success = False
                print(f"  ❌ Failed to stop PID {pid}: {error}")
        print()

    # Step 4: Kill any remaining port occupants
    if occupied_ports:
        print("  📍 Cleaning occupied ports...")
        for port in occupied_ports.keys():
            occupant_pid = lifecycle.port_occupant_pid(port)
            results = (
                kill_processes_safely(lifecycle, {occupant_pid}, timeout_seconds=5.0)
                if occupant_pid is not None
                else ()
            )
            success, error = (results[0][1], results[0][2]) if results else (True, None)
            if success:
                print(f"  ✅ Port {port} cleared")
            else:
                all_success = False
                print(f"  ❌ Port {port} cleanup failed: {error}")
        print()

    # Step 5: Clean up PID files
    print("  📍 Cleaning up stale files...")
    cleaned_files = cleanup_pid_files(lifecycle)
    if cleaned_files:
        for msg in cleaned_files:
            print(f"  ✅ {msg}")
    else:
        print("  ✅ No stale files found")
    print()

    # Step 6: Verify ports are released
    print("  📍 Verifying port status...")
    time.sleep(1.0)

    if lifecycle.ports_in_use(ports):
        all_success = False
        print("  ⚠️  Some ports are still occupied after cleanup")

        still_occupied = diagnose_ports(lifecycle, ports)
        if still_occupied:
            for port, remaining_info in still_occupied.items():
                print(f"  - Port {port} still occupied by PID {remaining_info}")
    else:
        print("  ✅ All ports are now available")

    return all_success


def run_doctor_with_port_fix(
    lifecycle: LifecycleFacade,
    fix_ports: bool = False,
    force: bool = False,
) -> int:
    """Run doctor with optional port cleanup."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()

    # Port diagnostics first
    if fix_ports:
        if not interactive_port_cleanup(lifecycle, force=force):
            print()
            print("  ❌ Port cleanup failed or cancelled")
            return 1
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
