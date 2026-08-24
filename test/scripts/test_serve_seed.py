from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path
from typing import Any

from scripts import serve


class _CapturingLifecycle:
    def __init__(self) -> None:
        self.registrations: list[Path] = []
        self.calls: list[Any] = []

    def register_current_service(self, elfie_home: Path) -> None:
        self.registrations.append(elfie_home)

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


class _FailingEndpoints:
    def close(self) -> None:
        raise OSError("endpoint close failed")


class _EngineProgress:
    completed_ticks = 4
    last_tick_duration_seconds = 0.25


class _StalledEngine:
    tick_interval_sec = 1.5
    is_running = True
    stop_requested = False

    @staticmethod
    def progress_snapshot() -> _EngineProgress:
        return _EngineProgress()

    @staticmethod
    def progress_age_seconds(*, now: float) -> float:
        del now
        return 10.0


class _CapturingDiagnostics:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.exceptions: list[tuple[str, BaseException]] = []
        self.dumps: list[str] = []

    def event(self, event: str, **_fields: object) -> None:
        self.events.append(event)

    def exception(self, event: str, error: BaseException, **_fields: object) -> None:
        self.exceptions.append((event, error))

    def dump_all_thread_traces(self, *, reason: str) -> bool:
        self.dumps.append(reason)
        return True


class _OrderedCleanup:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def cleanup(self) -> None:
        self.calls.append("cleanup")


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


def test_foreground_core_registers_its_own_process_receipt(tmp_path: Path) -> None:
    lifecycle = _CapturingLifecycle()

    serve.register_service_process_for_start(
        lifecycle,
        tmp_path,
        managed_start=False,
    )

    assert lifecycle.registrations == [tmp_path]


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


def test_startup_cleanup_records_socket_failure_and_continues_to_receipt(
    caplog,
    tmp_path: Path,
) -> None:
    lifecycle = _CapturingLifecycle()
    cleanup = serve.RuntimeStartupCleanup(
        lifecycle,
        tmp_path,
        managed_start=False,
    )
    cleanup.endpoint_sockets = _FailingEndpoints()
    cleanup.receipt_registered = True
    caplog.set_level(logging.ERROR, logger="elfienest.diagnostics.core_cleanup")

    cleanup.cleanup()

    assert lifecycle.calls == [("receipt", tmp_path)]
    assert any(
        getattr(record, "diagnostic_event", "") == "endpoint_socket_cleanup_failed"
        for record in caplog.records
    )


def test_engine_watchdog_confirms_a_stall_and_records_thread_traces() -> None:
    failure = serve.EngineFailureSignal()
    diagnostics = _CapturingDiagnostics()

    serve.monitor_engine_progress(
        _StalledEngine(),
        failure,
        threading.Event(),
        diagnostics,  # type: ignore[arg-type]
        poll_seconds=0.001,
        confirmation_seconds=0.0,
        heartbeat_seconds=60.0,
        stall_threshold_seconds=0.0,
    )

    assert isinstance(failure.error, serve.EngineStalledError)
    assert diagnostics.dumps == ["engine_stall_suspected"]
    assert [event for event, _error in diagnostics.exceptions] == [
        "engine_stalled_fatal"
    ]


def test_engine_failure_bridge_requests_uvicorn_shutdown() -> None:
    failure = serve.EngineFailureSignal()
    shutdown = threading.Event()
    server = type("Server", (), {"should_exit": False})()
    failure.fail(RuntimeError("tick failed"))

    serve.stop_server_on_engine_failure(failure, shutdown, server)

    assert server.should_exit is True


def test_unavailable_structured_diagnostics_do_not_abort_core_startup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _UnavailableDiagnostics:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise OSError("log directory unavailable")

    monkeypatch.setattr(serve, "ProcessDiagnostics", _UnavailableDiagnostics)

    assert serve._open_core_diagnostics(tmp_path) is None


def test_core_shutdown_events_bracket_runtime_cleanup() -> None:
    calls: list[str] = []

    class OrderedDiagnostics(_CapturingDiagnostics):
        def event(self, event: str, **_fields: object) -> None:
            calls.append(event)

    serve._finalize_core_runtime(
        _OrderedCleanup(calls),  # type: ignore[arg-type]
        OrderedDiagnostics(),  # type: ignore[arg-type]
        fatal_exit=False,
    )

    assert calls == ["core_process_stopping", "cleanup", "core_process_stopped"]


def test_managed_core_sigterm_handler_records_shutdown_request() -> None:
    diagnostics = _CapturingDiagnostics()
    previous = signal.getsignal(signal.SIGTERM)
    restore = serve._install_managed_core_sigterm_handler(
        diagnostics,  # type: ignore[arg-type]
    )
    try:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
    finally:
        restore()

    assert signal.getsignal(signal.SIGTERM) is previous
    assert diagnostics.events == ["core_shutdown_requested"]
