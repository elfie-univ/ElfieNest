"""Small Windows Job Object adapter for owned process-tree cleanup.

The module is importable on every platform, but the native calls are made only
on Windows.  A Job Object is configured to terminate its members when the
last owner handle closes; lifecycle still performs graceful/forced stop and
uses the Job as the bounded tree-cleanup backstop.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_QUERY = 0x0004
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001


class WindowsJobObject:
    """Own one native Job Object handle."""

    def __init__(self, handle: int, name: str) -> None:
        self._handle = handle
        self.name = name

    @classmethod
    def create(cls, name: str) -> WindowsJobObject:
        if os.name != "nt":
            raise OSError("Windows Job Objects are unavailable on this platform")
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        handle = kernel32.CreateJobObjectW(None, wintypes.LPCWSTR(name))
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not configured:
            error = ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
            kernel32.CloseHandle(handle)
            raise error
        return cls(int(handle), name)

    @classmethod
    def open(cls, name: str) -> WindowsJobObject:
        """Open a named Job so a managed child can retain its lifetime handle."""
        if os.name != "nt":
            raise OSError("Windows Job Objects are unavailable on this platform")
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.OpenJobObjectW.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.OpenJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.OpenJobObjectW(
            JOB_OBJECT_QUERY,
            False,
            wintypes.LPCWSTR(name),
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        return cls(int(handle), name)

    def assign(self, pid: int) -> None:
        if os.name != "nt":
            raise OSError("Windows Job Objects are unavailable on this platform")
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        process = kernel32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE,
            False,
            pid,
        )
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        try:
            assigned = kernel32.AssignProcessToJobObject(self._handle, process)
            if not assigned:
                raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        finally:
            kernel32.CloseHandle(process)

    def terminate(self, *, exit_code: int = 1) -> None:
        if os.name != "nt":
            return
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        if not kernel32.TerminateJobObject(self._handle, exit_code):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]

    def close(self) -> None:
        if not self._handle or os.name != "nt":
            return
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(  # type: ignore[attr-defined]
            self._handle
        )
        self._handle = 0

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def attach_process_to_job(pid: int, name: str) -> Optional[WindowsJobObject]:
    """Create a kill-on-close Job and attach exactly one launched root."""
    if os.name != "nt":
        return None
    job = WindowsJobObject.create(name)
    try:
        job.assign(pid)
    except Exception:
        job.close()
        raise
    return job


def deterministic_job_name(namespace: str, identity: str) -> str:
    """Return a stable per-user local name without embedding paths or secrets."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"Local\\ElfieNest.{namespace}.{digest}"


__all__ = (
    "WindowsJobObject",
    "attach_process_to_job",
    "deterministic_job_name",
)
