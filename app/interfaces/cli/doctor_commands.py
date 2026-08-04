"""Local doctor diagnostics and safe auto-repair entry."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set, Tuple

from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_elfie_home,
    get_logs_dir,
    get_model_validation_dir,
    get_runtime_locks_dir,
    get_runtime_validation_dir,
)
from app.orchestration.lifecycle.process import (
    DEFAULT_SERVICE_PORTS,
    PID_FILENAME,
    DefaultProcessInspector,
    any_service_port_in_use,
    get_port_occupant_pid,
    kill_port_occupant,
)


@dataclass(frozen=True)
class DoctorRepairReport:
    """Summary of local auto-repair actions."""

    repaired: tuple[str, ...] = ()


def run_doctor() -> int:
    """Run safe local repairs first, then offline runtime and config checks."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()
    try:
        repairs = repair_local_runtime_state()
        if repairs.repaired:
            print("  🔧 Auto-repaired:")
            for item in repairs.repaired:
                print(f"    - {item}")
            print()
        else:
            print("  ✅ Local structure needs no repair")
            print()
        report = RuntimeLab().run_offline_validation()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"  ❌ Doctor failed: {error}")
        return 1
    print(
        "  ✅ Repair and diagnostics complete"
        if report.passed
        else "  ⚠️  Repair complete, diagnostics found issues"
    )
    return 0 if report.passed else 1


def repair_local_runtime_state() -> DoctorRepairReport:
    """Repair local state that needs no network, keys, or user data deletion."""
    repaired: list[str] = []
    expected_dirs = (
        get_elfie_home(),
        get_elfie_home() / "assets",
        get_elfie_home() / "assets" / "users",
        get_elfie_home() / "configs",
        get_elfie_home() / "elfies",
        get_logs_dir(),
        get_model_validation_dir(),
        get_runtime_validation_dir(),
        get_runtime_locks_dir(),
    )
    missing_dirs = [path for path in expected_dirs if not path.exists()]
    ensure_elfie_home()
    if missing_dirs:
        repaired.append("Created missing ~/.elfienest data directories")

    return DoctorRepairReport(tuple(repaired))


@dataclass(frozen=True)
class ProcessInfo:
    """Information about a running process."""

    pid: int
    command: Tuple[str, ...]
    cwd: Optional[Path]
    process_type: str  # "python", "electron", "other"


def find_all_elfienest_processes() -> Tuple[ProcessInfo, ...]:
    """
    Find all ElfieNest background service processes.

    Only includes:
    - Python service processes running scripts/serve.py
    - Electron processes running godot-authority role
    - Electron helper processes spawned by godot-authority
    """
    processes: list[ProcessInfo] = []
    inspector = DefaultProcessInspector()
    current_pid = os.getpid()
    godot_authority_pids: set[int] = set()

    try:
        result = subprocess.run(
            ["ps", "aux"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )

        # First pass: identify main processes
        for line in result.stdout.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue

            pid_str = parts[1]
            command = parts[10]

            try:
                pid = int(pid_str)
            except ValueError:
                continue

            if pid == current_pid:
                continue

            is_elfienest = False
            process_type = "other"

            # Python service process
            if "scripts/serve.py" in command or "scripts\\serve.py" in command:
                is_elfienest = True
                process_type = "python"
            # Electron godot-authority process
            elif "--elfienest-role=godot-authority" in command:
                is_elfienest = True
                process_type = "electron"
                godot_authority_pids.add(pid)

            if is_elfienest:
                try:
                    cmd_tuple = tuple(command.split())
                    cwd = inspector.cwd(pid) if inspector.exists(pid) else None
                    processes.append(
                        ProcessInfo(
                            pid=pid,
                            command=cmd_tuple,
                            cwd=cwd,
                            process_type=process_type,
                        )
                    )
                except (OSError, subprocess.SubprocessError):
                    processes.append(
                        ProcessInfo(
                            pid=pid,
                            command=(command,),
                            cwd=None,
                            process_type=process_type,
                        )
                    )

        # Second pass: find Electron helper processes
        if godot_authority_pids:
            for line in result.stdout.splitlines()[1:]:
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue

                pid_str = parts[1]
                ppid_str = parts[2]
                command = parts[10]

                try:
                    pid = int(pid_str)
                    ppid = int(ppid_str)
                except ValueError:
                    continue

                if pid == current_pid or any(p.pid == pid for p in processes):
                    continue

                if ppid in godot_authority_pids and "Electron" in command:
                    try:
                        cmd_tuple = tuple(command.split())
                        cwd = inspector.cwd(pid) if inspector.exists(pid) else None
                        processes.append(
                            ProcessInfo(
                                pid=pid,
                                command=cmd_tuple,
                                cwd=cwd,
                                process_type="electron",
                            )
                        )
                    except (OSError, subprocess.SubprocessError):
                        processes.append(
                            ProcessInfo(
                                pid=pid,
                                command=(command,),
                                cwd=None,
                                process_type="electron",
                            )
                        )

    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass

    return tuple(processes)


def kill_processes_safely(
    pids: Set[int],
    timeout_seconds: float = 10.0,
) -> Tuple[Tuple[int, bool, Optional[str]], ...]:
    """Kill a set of processes safely with proper timeout."""
    results: list[Tuple[int, bool, Optional[str]]] = []
    inspector = DefaultProcessInspector()

    for pid in pids:
        try:
            if not inspector.exists(pid):
                results.append((pid, True, None))
                continue

            os.kill(pid, signal.SIGTERM)
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
            if not inspector.exists(pid):
                still_running.remove(pid)
        if still_running:
            time.sleep(0.1)

    # Force kill remaining processes
    if still_running:
        for pid in still_running:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        time.sleep(0.5)

    # Update results
    final_results: list[Tuple[int, bool, Optional[str]]] = []
    for pid, _, error_message in results:
        if error_message:
            final_results.append((pid, False, error_message))
        elif inspector.exists(pid):
            final_results.append((pid, False, "Process did not exit"))
        else:
            final_results.append((pid, True, None))

    return tuple(final_results)


def cleanup_pid_files() -> Tuple[str, ...]:
    """Clean up stale PID files."""
    cleaned: list[str] = []
    elfie_home = get_elfie_home()
    pid_path = elfie_home / PID_FILENAME

    if pid_path.exists():
        try:
            pid_path.unlink()
            cleaned.append(f"Removed stale PID file: {pid_path}")
        except OSError as error:
            cleaned.append(f"Failed to remove PID file: {error}")

    return tuple(cleaned)


def diagnose_ports(ports: Tuple[int, ...] = DEFAULT_SERVICE_PORTS) -> dict:
    """
    Diagnose port occupation.

    Returns:
        Dict mapping port -> ProcessInfo (or None if not occupied)
    """
    from app.orchestration.lifecycle.process import DefaultProcessInspector

    occupied = {}
    inspector = DefaultProcessInspector()

    for port in ports:
        pid = get_port_occupant_pid(port)
        if pid:
            try:
                # Get process details
                command = inspector.command(pid)
                cwd = inspector.cwd(pid) if inspector.exists(pid) else None

                occupied[port] = ProcessInfo(
                    pid=pid,
                    command=command,
                    cwd=cwd,
                    process_type="unknown",
                )
            except (OSError, subprocess.SubprocessError):
                # If we can't get details, just record the PID
                occupied[port] = ProcessInfo(
                    pid=pid,
                    command=(),
                    cwd=None,
                    process_type="unknown",
                )

    return occupied


def interactive_port_cleanup(
    ports: Tuple[int, ...] = DEFAULT_SERVICE_PORTS,
    *,
    force: bool = False,
) -> bool:
    """Interactively clean up all ElfieNest-related processes and ports."""
    # Step 1: Find all ElfieNest-related processes
    all_processes = find_all_elfienest_processes()

    # Step 2: Check port occupation
    occupied_ports = diagnose_ports(ports)

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
        kill_results = kill_processes_safely(pids, timeout_seconds=10.0)

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
            success, error = kill_port_occupant(port, timeout_seconds=5.0)
            if success:
                print(f"  ✅ Port {port} cleared")
            else:
                all_success = False
                print(f"  ❌ Port {port} cleanup failed: {error}")
        print()

    # Step 5: Clean up PID files
    print("  📍 Cleaning up stale files...")
    cleaned_files = cleanup_pid_files()
    if cleaned_files:
        for msg in cleaned_files:
            print(f"  ✅ {msg}")
    else:
        print("  ✅ No stale files found")
    print()

    # Step 6: Verify ports are released
    print("  📍 Verifying port status...")
    time.sleep(1.0)

    if any_service_port_in_use(ports):
        all_success = False
        print("  ⚠️  Some ports are still occupied after cleanup")

        still_occupied = diagnose_ports(ports)
        if still_occupied:
            for port, pid in still_occupied.items():
                print(f"  - Port {port} still occupied by PID {pid}")
    else:
        print("  ✅ All ports are now available")

    return all_success


def run_doctor_with_port_fix(fix_ports: bool = False, force: bool = False) -> int:
    """Run doctor with optional port cleanup."""
    print("  🩺 Doctor diagnostics and auto-repair")
    print("  " + "=" * 45)
    print()

    # Port diagnostics first
    if fix_ports:
        if not interactive_port_cleanup(force=force):
            print()
            print("  ❌ Port cleanup failed or cancelled")
            return 1
        print()

    # Original doctor repairs
    try:
        repairs = repair_local_runtime_state()
        if repairs.repaired:
            print("  🔧 Auto-repaired:")
            for item in repairs.repaired:
                print(f"    - {item}")
            print()
        else:
            print("  ✅ Local structure needs no repair")
            print()

        report = RuntimeLab().run_offline_validation()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"  ❌ Doctor failed: {error}")
        return 1

    print(
        "  ✅ Repair and diagnostics complete"
        if report.passed
        else "  ⚠️  Repair complete, diagnostics found issues"
    )
    return 0 if report.passed else 1
