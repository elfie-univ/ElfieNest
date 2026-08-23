from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import serve


class _CapturingLifecycle:
    def __init__(self) -> None:
        self.registrations: list[Path] = []
        self.retentions = 0
        self.calls: list[Any] = []

    def register_current_service(self, elfie_home: Path) -> None:
        self.registrations.append(elfie_home)

    def retain_current_service_process(self) -> None:
        self.retentions += 1

    def stop_runtime_channel(self, channel: object) -> None:
        self.calls.append(("channel", channel))

    def clear_receipt(self, elfie_home: Path) -> None:
        self.calls.append(("receipt", elfie_home))


class _WorldWorker:
    def __init__(self, calls: list[str], detail: str | None = None) -> None:
        self.calls = calls
        self.detail = detail

    def stop(self) -> str | None:
        self.calls.append("world")
        return self.detail


class _Lease:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def release(self) -> None:
        self.calls.append("lease")


class _Joinable:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def join(self, *, timeout: float) -> None:
        self.calls.append(f"join:{timeout}")


def test_managed_core_leaves_the_process_receipt_owned_by_its_supervisor(
    tmp_path: Path,
) -> None:
    lifecycle = _CapturingLifecycle()

    serve.register_service_process_for_start(
        lifecycle,
        tmp_path,
        managed_start=True,
    )

    assert lifecycle.registrations == []
    assert lifecycle.retentions == 1


def test_foreground_core_registers_its_own_process_receipt(tmp_path: Path) -> None:
    lifecycle = _CapturingLifecycle()

    serve.register_service_process_for_start(
        lifecycle,
        tmp_path,
        managed_start=False,
    )

    assert lifecycle.registrations == [tmp_path]
    assert lifecycle.retentions == 0


def test_startup_cleanup_releases_each_acquired_resource_once(tmp_path: Path) -> None:
    lifecycle = _CapturingLifecycle()
    calls: list[str] = []
    cleanup = serve.RuntimeStartupCleanup(
        lifecycle,
        tmp_path,
        managed_start=False,
    )
    cleanup.receipt_registered = True
    cleanup.world_worker = _WorldWorker(calls)
    cleanup.optional_lease_thread = _Joinable(calls)
    cleanup.optional_lease = _Lease(calls)
    cleanup.world_runtime = object()

    cleanup.cleanup()
    cleanup.cleanup()

    assert calls == ["world", "join:1.0", "lease"]
    assert lifecycle.calls == [
        ("channel", cleanup.world_runtime),
        ("receipt", tmp_path),
    ]


def test_managed_startup_cleanup_leaves_receipt_to_parent(tmp_path: Path) -> None:
    lifecycle = _CapturingLifecycle()
    cleanup = serve.RuntimeStartupCleanup(
        lifecycle,
        tmp_path,
        managed_start=True,
    )
    cleanup.receipt_registered = True

    cleanup.cleanup()

    assert lifecycle.calls == []
