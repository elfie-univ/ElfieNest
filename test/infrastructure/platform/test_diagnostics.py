from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path

from infrastructure.platform.diagnostics import (
    ProcessDiagnostics,
    redact_diagnostic_text,
    sample_process_resources,
)


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_process_diagnostics_writes_structured_redacted_events(tmp_path: Path) -> None:
    diagnostics = ProcessDiagnostics(
        tmp_path,
        role="core",
        source_revision="a" * 40,
    )
    try:
        try:
            raise RuntimeError(
                "request https://example.test/path?token=visible password=hunter2"
            )
        except RuntimeError as error:
            diagnostics.exception(
                "engine_loop_failed",
                error,
                generation=7,
                phase="world_ready",
            )
    finally:
        diagnostics.close()

    log_path = tmp_path / "logs" / "core-events.jsonl"
    payload = _events(log_path)[0]
    encoded = json.dumps(payload, ensure_ascii=False)
    assert payload["event"] == "engine_loop_failed"
    assert payload["role"] == "core"
    assert payload["generation"] == 7
    assert payload["source_revision"] == "a" * 40
    assert payload["pid"] > 0
    assert "visible" not in encoded
    assert "hunter2" not in encoded
    assert "?<redacted>" in encoded
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert log_path.parent.stat().st_mode & 0o777 == 0o700


def test_process_diagnostics_bounds_one_pathological_exception_record(
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    try:
        try:
            raise RuntimeError("x" * 30_000)
        except RuntimeError as error:
            diagnostics.exception(
                "engine_loop_failed",
                error,
                reason="y" * 5_000,
            )
    finally:
        diagnostics.close()

    payload = _events(tmp_path / "logs" / "core-events.jsonl")[0]
    assert len(str(payload["message"])) <= 4_096
    assert len(str(payload["exception"])) <= 16_384
    assert len(str(payload["reason"])) <= 512


def test_process_diagnostics_rotates_with_a_fixed_backup_cap(tmp_path: Path) -> None:
    diagnostics = ProcessDiagnostics(
        tmp_path,
        role="core",
        max_bytes=512,
        backup_count=2,
    )
    try:
        for index in range(40):
            diagnostics.event(
                "resource_sample",
                message=f"sample-{index}-" + ("x" * 120),
            )
    finally:
        diagnostics.close()

    logs = sorted((tmp_path / "logs").glob("core-events.jsonl*"))
    assert [path.name for path in logs] == [
        "core-events.jsonl",
        "core-events.jsonl.1",
        "core-events.jsonl.2",
    ]


def test_root_warning_log_is_structured_redacted_and_separate_from_events(
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    diagnostics.configure_root_warning_log()
    try:
        logging.getLogger("some.component").error(
            "request failed https://example.test/api?token=visible"
        )
    finally:
        diagnostics.close()

    encoded = (tmp_path / "logs" / "service.log").read_text(encoding="utf-8")
    payload = json.loads(encoded)
    assert payload["logger"] == "some.component"
    assert payload["level"] == "error"
    assert "visible" not in encoded
    assert "?<redacted>" in encoded


def test_unavailable_root_warning_log_does_not_abort_core_diagnostics(
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    (tmp_path / "logs" / "service.log").mkdir()
    try:
        diagnostics.configure_root_warning_log()
    finally:
        diagnostics.close()

    events = _events(tmp_path / "logs" / "core-events.jsonl")
    assert events[-1]["event"] == "root_warning_log_unavailable"
    assert events[-1]["error_type"] == "IsADirectoryError"


def test_asyncio_failures_enter_the_same_redacted_diagnostic_stream(
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    loop = asyncio.new_event_loop()
    restore = diagnostics.install_asyncio_exception_handler(loop)
    try:
        loop.call_exception_handler(
            {
                "message": "background task failed",
                "exception": RuntimeError("api_key=do-not-store"),
            }
        )
    finally:
        restore()
        loop.close()
        diagnostics.close()

    encoded = (tmp_path / "logs" / "core-events.jsonl").read_text(encoding="utf-8")
    assert "asyncio_unhandled_exception" in encoded
    assert "do-not-store" not in encoded


def test_asyncio_diagnostics_preserve_the_existing_handler_on_log_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    loop = asyncio.new_event_loop()
    observed: list[str] = []

    def previous_handler(
        _loop: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        observed.append(str(context["message"]))

    def fail_diagnostic(*_args: object, **_kwargs: object) -> None:
        raise OSError("log failed")

    loop.set_exception_handler(previous_handler)
    monkeypatch.setattr(diagnostics, "exception", fail_diagnostic)
    restore = diagnostics.install_asyncio_exception_handler(loop)
    try:
        loop.call_exception_handler(
            {
                "message": "original loop handler",
                "exception": RuntimeError("task failed"),
            }
        )
    finally:
        restore()
        loop.close()
        diagnostics.close()

    assert observed == ["original loop handler"]


def test_process_resource_sample_is_lightweight_and_path_safe(tmp_path: Path) -> None:
    sample = sample_process_resources(
        tmp_path,
        started_at=time.monotonic() - 2.0,
    )

    assert sample["uptime_seconds"] >= 1.0
    assert sample["thread_count"] >= 1
    assert sample.get("peak_rss_bytes", 0) >= 0
    assert sample["disk_free_bytes"] >= 0
    assert "path" not in sample


def test_resource_monitor_recovers_after_one_sample_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from infrastructure.platform import diagnostics as diagnostics_module

    recovered = threading.Event()
    calls = 0

    def sample(_home: Path, *, started_at: float) -> dict[str, object]:
        nonlocal calls
        del started_at
        calls += 1
        if calls == 1:
            raise OSError("temporary resource probe failure")
        recovered.set()
        return {
            "uptime_seconds": 1.0,
            "thread_count": 1,
            "peak_rss_bytes": 1,
            "cpu_user_seconds": 0.0,
            "cpu_system_seconds": 0.0,
            "disk_free_bytes": 2 * 1024 * 1024 * 1024,
            "disk_total_bytes": 4 * 1024 * 1024 * 1024,
            "open_fd_count": 1,
        }

    monkeypatch.setattr(diagnostics_module, "sample_process_resources", sample)
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    try:
        diagnostics.start_resource_monitor(interval_seconds=0.001)
        assert recovered.wait(timeout=1.0) is True
    finally:
        diagnostics.close()

    events = _events(tmp_path / "logs" / "core-events.jsonl")
    assert [event["event"] for event in events[:2]] == [
        "resource_monitor_sample_failed",
        "process_resource_sample",
    ]


def test_process_diagnostics_does_not_replace_an_existing_faulthandler(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from infrastructure.platform import diagnostics as diagnostics_module

    enable_calls = 0
    disable_calls = 0

    def enable(**_kwargs: object) -> None:
        nonlocal enable_calls
        enable_calls += 1

    def disable() -> None:
        nonlocal disable_calls
        disable_calls += 1

    monkeypatch.setattr(diagnostics_module.faulthandler, "is_enabled", lambda: True)
    monkeypatch.setattr(diagnostics_module.faulthandler, "enable", enable)
    monkeypatch.setattr(diagnostics_module.faulthandler, "disable", disable)
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    try:
        diagnostics.install_exception_hooks()
    finally:
        diagnostics.close()

    assert enable_calls == 0
    assert disable_calls == 0


def test_redaction_covers_quoted_mapping_assignments() -> None:
    source = (
        '"api_key": "double-secret", '
        "'token': 'single-secret', password=plain-secret"
    )

    redacted = redact_diagnostic_text(source)

    assert "double-secret" not in redacted
    assert "single-secret" not in redacted
    assert "plain-secret" not in redacted
    assert redacted.count("<redacted>") == 3


def test_redaction_covers_oauth_credentials_and_authorization_headers() -> None:
    source = (
        "access_token=sample-access "
        "refresh_token='sample-refresh' "
        '"client_secret": "sample-client" '
        "Authorization: Bearer sample-bearer "
        "Bearer sample-standalone"
    )

    redacted = redact_diagnostic_text(source)

    for credential in (
        "sample-access",
        "sample-refresh",
        "sample-client",
        "sample-bearer",
        "sample-standalone",
    ):
        assert credential not in redacted
    assert redacted.count("<redacted>") >= 5


def test_runtime_identity_is_automatically_attached_to_later_events(
    tmp_path: Path,
) -> None:
    diagnostics = ProcessDiagnostics(tmp_path, role="core")
    try:
        diagnostics.bind_runtime_context(
            instance_id="runtime-7",
            generation=7,
            correlation_id="operation-7",
        )
        diagnostics.event("engine_progress", completed_ticks=12)
    finally:
        diagnostics.close()

    payload = _events(tmp_path / "logs" / "core-events.jsonl")[0]
    assert payload["instance_id"] == "runtime-7"
    assert payload["generation"] == 7
    assert payload["correlation_id"] == "operation-7"
    assert payload["completed_ticks"] == 12


def test_resource_sample_omits_platform_metrics_that_are_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from infrastructure.platform import diagnostics as diagnostics_module

    monkeypatch.setattr(diagnostics_module, "resource", None)
    monkeypatch.setattr(diagnostics_module, "_open_fd_count", lambda: None)

    sample = diagnostics_module.sample_process_resources(
        tmp_path,
        started_at=time.monotonic(),
    )

    assert "peak_rss_bytes" not in sample
    assert "cpu_user_seconds" not in sample
    assert "cpu_system_seconds" not in sample
    assert "open_fd_count" not in sample
