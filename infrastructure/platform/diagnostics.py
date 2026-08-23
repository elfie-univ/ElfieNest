"""Process-local, redacted diagnostics for long-running ElfieNest roles."""

from __future__ import annotations

import asyncio
import faulthandler
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Mapping, Optional, TextIO, TypedDict

try:  # ``resource`` is unavailable on Windows.
    import resource
except ImportError:  # pragma: no cover - exercised on Windows CI.
    resource = None  # type: ignore[assignment]


DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 4
DEFAULT_RESOURCE_SAMPLE_SECONDS = 300.0
_MAX_MESSAGE_CHARACTERS = 4_096
_MAX_EXCEPTION_CHARACTERS = 16_384
_MAX_FIELD_CHARACTERS = 512

_DIAGNOSTIC_LOGGER_NAME = "elfienest.diagnostics"
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?\b(?:api[_-]?key|token|nonce|password|secret|authorization)\b"
    r"[\"']?\s*[:=]\s*)"
    r"(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\]]+)"
)
_SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SAFE_FIELDS = frozenset(
    {
        "attempt",
        "capacity",
        "component",
        "completed_ticks",
        "core_pid",
        "correlation_id",
        "cpu_system_seconds",
        "cpu_user_seconds",
        "disk_free_bytes",
        "disk_total_bytes",
        "dropped_count",
        "duration_ms",
        "error_type",
        "exit_code",
        "generation",
        "instance_id",
        "last_progress_age_ms",
        "last_tick_duration_ms",
        "open_fd_count",
        "peak_rss_bytes",
        "phase",
        "queue_depth",
        "reason",
        "rejected_count",
        "revision",
        "rss_bytes",
        "signal",
        "status",
        "suppressed_count",
        "thread_count",
        "tier",
        "total_attempts",
        "uptime_seconds",
    }
)

SysExceptionHook = Callable[
    [type[BaseException], BaseException, Optional[TracebackType]],
    Any,
]
ThreadExceptionHook = Callable[[threading.ExceptHookArgs], Any]


class ProcessResourceSample(TypedDict, total=False):
    uptime_seconds: float
    thread_count: int
    peak_rss_bytes: int
    cpu_user_seconds: float
    cpu_system_seconds: float
    disk_free_bytes: int
    disk_total_bytes: int
    open_fd_count: int


def redact_diagnostic_text(value: str) -> str:
    """Remove common credential shapes and every URL query string."""
    redacted = _URL_QUERY.sub(r"\1?<redacted>", value)
    redacted = _BEARER.sub("Bearer <redacted>", redacted)

    def replace_assignment(match: re.Match[str]) -> str:
        prefix = match.group(1)
        assigned = match.group(2)
        if assigned.startswith('"'):
            return f'{prefix}"<redacted>"'
        if assigned.startswith("'"):
            return f"{prefix}'<redacted>'"
        return f"{prefix}<redacted>"

    return _SECRET_ASSIGNMENT.sub(replace_assignment, redacted)


class _SecureRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        try:
            if os.name != "nt":
                os.chmod(self.baseFilename, 0o600)
        except OSError:
            stream.close()
            raise
        return stream


class _DiagnosticJsonFormatter(logging.Formatter):
    def __init__(
        self,
        *,
        role: str,
        source_revision: str,
        context_provider: Callable[[], Mapping[str, object]],
    ) -> None:
        super().__init__()
        self._role = role
        self._source_revision = source_revision
        self._context_provider = context_provider

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "event": getattr(record, "diagnostic_event", "diagnostic_message"),
            "role": self._role,
            "pid": os.getpid(),
            "thread": record.threadName,
            "logger": record.name,
            "source_revision": self._source_revision,
        }
        message = redact_diagnostic_text(record.getMessage())[:_MAX_MESSAGE_CHARACTERS]
        if message:
            payload["message"] = message
        context = self._context_provider()
        for field in _SAFE_FIELDS:
            value = getattr(record, field, context.get(field))
            if isinstance(value, str):
                payload[field] = redact_diagnostic_text(value)[:_MAX_FIELD_CHARACTERS]
            elif isinstance(value, (int, float, bool)):
                payload[field] = value
        if record.exc_info is not None:
            payload["exception"] = redact_diagnostic_text(
                self.formatException(record.exc_info)
            )[:_MAX_EXCEPTION_CHARACTERS]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class ProcessDiagnostics:
    """Own one role's rotated event stream and fatal-process hooks."""

    def __init__(
        self,
        elfie_home: Path,
        *,
        role: str,
        source_revision: str | None = None,
        max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    ) -> None:
        if not role or not re.fullmatch(r"[a-z][a-z0-9_-]*", role):
            raise ValueError("diagnostic role must be a safe lowercase identifier")
        if max_bytes <= 0 or backup_count < 0:
            raise ValueError("diagnostic rotation limits must be positive")
        revision = (source_revision or "").strip().lower()
        self._source_revision = (
            revision if _SOURCE_REVISION.fullmatch(revision) else "unknown"
        )
        self._role = role
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._started_at = time.monotonic()
        self._context: dict[str, object] = {}
        self._log_dir = elfie_home.expanduser().resolve(strict=False) / "logs"
        self._log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            self._log_dir.chmod(0o700)
        self.log_path = self._log_dir / f"{role}-events.jsonl"
        self._handler = _SecureRotatingFileHandler(
            self.log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        self._handler.setFormatter(
            _DiagnosticJsonFormatter(
                role=role,
                source_revision=self._source_revision,
                context_provider=lambda: self._context,
            )
        )
        self._logger = logging.getLogger(_DIAGNOSTIC_LOGGER_NAME)
        self._previous_diagnostic_handlers = tuple(self._logger.handlers)
        self._previous_diagnostic_level = self._logger.level
        self._previous_diagnostic_propagate = self._logger.propagate
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        for existing in self._previous_diagnostic_handlers:
            self._logger.removeHandler(existing)
        self._logger.addHandler(self._handler)
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._root_handler: _SecureRotatingFileHandler | None = None
        self._previous_root_handlers: tuple[logging.Handler, ...] = ()
        self._previous_root_level: int | None = None
        self._fatal_stream: Optional[TextIO] = None
        self._faulthandler_owned = False
        self._previous_sys_hook: Optional[SysExceptionHook] = None
        self._previous_thread_hook: Optional[ThreadExceptionHook] = None
        self._sys_hook: Optional[SysExceptionHook] = None
        self._thread_hook: Optional[ThreadExceptionHook] = None
        self._closed = False

    def configure_root_warning_log(self) -> None:
        """Route Python warnings/errors to a separately rotated service log."""
        if self._root_handler is not None:
            return
        try:
            handler = _SecureRotatingFileHandler(
                self._log_dir / "service.log",
                maxBytes=self._max_bytes,
                backupCount=self._backup_count,
                encoding="utf-8",
            )
        except OSError as error:
            self.exception("root_warning_log_unavailable", error)
            return
        handler.setLevel(logging.WARNING)
        handler.setFormatter(
            _DiagnosticJsonFormatter(
                role=self._role,
                source_revision=self._source_revision,
                context_provider=lambda: self._context,
            )
        )
        root_logger = logging.getLogger()
        self._previous_root_handlers = tuple(root_logger.handlers)
        self._previous_root_level = root_logger.level
        for previous_handler in self._previous_root_handlers:
            root_logger.removeHandler(previous_handler)
        root_logger.setLevel(logging.WARNING)
        root_logger.addHandler(handler)
        self._root_handler = handler

    def bind_runtime_context(
        self,
        *,
        instance_id: str,
        generation: int,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Attach immutable Runtime identity to subsequent process-local events."""
        if not instance_id:
            raise ValueError("diagnostic instance_id must not be empty")
        if generation < 0:
            raise ValueError("diagnostic generation must be non-negative")
        context: dict[str, object] = {
            "instance_id": instance_id,
            "generation": generation,
        }
        if correlation_id:
            context["correlation_id"] = correlation_id
        self._context = context

    def dump_all_thread_traces(self, *, reason: str) -> bool:
        """Append all Python thread stacks without making diagnostics authoritative."""
        stream = self._fatal_stream
        if stream is None:
            return False
        try:
            self.event(
                "thread_trace_dump",
                level=logging.WARNING,
                reason=reason,
            )
            faulthandler.dump_traceback(file=stream, all_threads=True)
            stream.flush()
        except (OSError, RuntimeError, ValueError) as error:
            self.exception(
                "thread_trace_dump_failed",
                error,
                level=logging.WARNING,
                reason=reason,
            )
            return False
        return True

    def event(
        self,
        event: str,
        *,
        level: int = logging.INFO,
        message: str = "",
        **fields: object,
    ) -> None:
        merged_fields = {**self._context, **fields}
        unknown = set(merged_fields) - _SAFE_FIELDS
        if unknown:
            raise ValueError(f"unsupported diagnostic fields: {sorted(unknown)}")
        self._logger.log(
            level,
            message,
            extra={"diagnostic_event": event, **merged_fields},
        )

    def exception(
        self,
        event: str,
        error: BaseException,
        *,
        level: int = logging.ERROR,
        **fields: object,
    ) -> None:
        fields.setdefault("error_type", type(error).__name__)
        merged_fields = {**self._context, **fields}
        unknown = set(merged_fields) - _SAFE_FIELDS
        if unknown:
            raise ValueError(f"unsupported diagnostic fields: {sorted(unknown)}")
        traceback: Optional[TracebackType] = error.__traceback__
        self._logger.log(
            level,
            str(error),
            exc_info=(type(error), error, traceback),
            extra={"diagnostic_event": event, **merged_fields},
        )

    def install_exception_hooks(self) -> None:
        """Capture uncaught Python and thread exceptions before normal termination."""
        if self._sys_hook is not None:
            return
        self._previous_sys_hook = sys.excepthook
        self._previous_thread_hook = threading.excepthook

        def sys_hook(
            exception_type: type[BaseException],
            exception: BaseException,
            traceback: Optional[TracebackType],
        ) -> None:
            self._logger.critical(
                str(exception),
                exc_info=(exception_type, exception, traceback),
                extra={
                    "diagnostic_event": "process_uncaught_exception",
                    "error_type": exception_type.__name__,
                    **self._context,
                },
            )
            previous = self._previous_sys_hook
            if previous is not None:
                previous(exception_type, exception, traceback)

        def thread_hook(args: threading.ExceptHookArgs) -> None:
            if args.exc_value is None:
                self._logger.critical(
                    "thread terminated without an exception value",
                    extra={
                        "diagnostic_event": "thread_uncaught_exception",
                        **self._context,
                    },
                )
            else:
                self._logger.critical(
                    str(args.exc_value),
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                    extra={
                        "diagnostic_event": "thread_uncaught_exception",
                        "error_type": args.exc_type.__name__,
                        **self._context,
                    },
                )
            previous = self._previous_thread_hook
            if previous is not None:
                previous(args)

        self._sys_hook = sys_hook
        self._thread_hook = thread_hook
        sys.excepthook = sys_hook
        threading.excepthook = thread_hook
        self._install_faulthandler()

    def install_asyncio_exception_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> Callable[[], None]:
        previous = loop.get_exception_handler()

        def handler(
            _loop: asyncio.AbstractEventLoop,
            context: Mapping[str, object],
        ) -> None:
            try:
                exception = context.get("exception")
                if isinstance(exception, BaseException):
                    self.exception("asyncio_unhandled_exception", exception)
                else:
                    self.event(
                        "asyncio_unhandled_exception",
                        level=logging.ERROR,
                        message=str(context.get("message", "asyncio task failed")),
                    )
            except (OSError, RuntimeError, ValueError):
                # Preserve the loop's original failure path even if the
                # supplemental diagnostic sink becomes unavailable.
                pass
            if previous is None:
                _loop.default_exception_handler(dict(context))
            else:
                previous(_loop, dict(context))

        loop.set_exception_handler(handler)

        def restore() -> None:
            if loop.get_exception_handler() is handler:
                loop.set_exception_handler(previous)

        return restore

    def start_resource_monitor(
        self,
        *,
        interval_seconds: float = DEFAULT_RESOURCE_SAMPLE_SECONDS,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("resource sample interval must be positive")
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()

        def monitor() -> None:
            consecutive_failures = 0
            while not self._monitor_stop.is_set():
                try:
                    fields = sample_process_resources(
                        self._log_dir.parent,
                        started_at=self._started_at,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    consecutive_failures += 1
                    if consecutive_failures & (consecutive_failures - 1) == 0:
                        self.exception(
                            "resource_monitor_sample_failed",
                            error,
                            level=logging.WARNING,
                            attempt=consecutive_failures,
                            component="process_resource_monitor",
                        )
                    if self._monitor_stop.wait(interval_seconds):
                        return
                    continue
                consecutive_failures = 0
                self.event("process_resource_sample", **fields)
                disk_free_bytes = int(fields["disk_free_bytes"])
                if disk_free_bytes < 1024 * 1024 * 1024:
                    self.event(
                        "resource_threshold",
                        level=logging.WARNING,
                        message="diagnostic data root has less than 1 GiB free",
                        disk_free_bytes=disk_free_bytes,
                    )
                if self._monitor_stop.wait(interval_seconds):
                    return

        self._monitor_thread = threading.Thread(
            target=monitor,
            name=f"ElfieNest-{self._role}-ResourceMonitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._monitor_stop.set()
        thread = self._monitor_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        previous_sys_hook = self._previous_sys_hook
        if (
            self._sys_hook is not None
            and sys.excepthook is self._sys_hook
            and previous_sys_hook is not None
        ):
            sys.excepthook = previous_sys_hook
        previous_thread_hook = self._previous_thread_hook
        if (
            self._thread_hook is not None
            and threading.excepthook is self._thread_hook
            and previous_thread_hook is not None
        ):
            threading.excepthook = previous_thread_hook
        if self._fatal_stream is not None:
            if self._faulthandler_owned and faulthandler.is_enabled():
                faulthandler.disable()
            self._fatal_stream.close()
            self._fatal_stream = None
            self._faulthandler_owned = False
        if self._root_handler is not None:
            root_logger = logging.getLogger()
            if self._root_handler in root_logger.handlers:
                root_logger.removeHandler(self._root_handler)
            self._root_handler.close()
            self._root_handler = None
            for handler in self._previous_root_handlers:
                if handler not in root_logger.handlers:
                    root_logger.addHandler(handler)
            if self._previous_root_level is not None:
                root_logger.setLevel(self._previous_root_level)
        if self._handler in self._logger.handlers:
            self._logger.removeHandler(self._handler)
        self._handler.close()
        for handler in self._previous_diagnostic_handlers:
            if handler not in self._logger.handlers:
                self._logger.addHandler(handler)
        self._logger.setLevel(self._previous_diagnostic_level)
        self._logger.propagate = self._previous_diagnostic_propagate

    def _install_faulthandler(self) -> None:
        if faulthandler.is_enabled():
            return
        fatal_path = self._log_dir / f"{self._role}-fatal.log"
        stream: Optional[TextIO] = None
        try:
            _rotate_at_start(
                fatal_path,
                max_bytes=DEFAULT_LOG_MAX_BYTES,
                backup_count=2,
            )
            stream = fatal_path.open("a", encoding="utf-8")
            if os.name != "nt":
                fatal_path.chmod(0o600)
            faulthandler.enable(file=stream, all_threads=True)
        except (OSError, RuntimeError) as error:
            if stream is not None:
                stream.close()
            self.exception(
                "faulthandler_unavailable",
                error,
                level=logging.WARNING,
                component="python_faulthandler",
            )
            return
        assert stream is not None
        self._fatal_stream = stream
        self._faulthandler_owned = True


def sample_process_resources(
    elfie_home: Path,
    *,
    started_at: float,
) -> ProcessResourceSample:
    """Collect a small stdlib-only stability sample without reading user data."""
    usage = resource.getrusage(resource.RUSAGE_SELF) if resource is not None else None
    disk = shutil.disk_usage(elfie_home)
    sample: ProcessResourceSample = {
        "uptime_seconds": max(0.0, time.monotonic() - started_at),
        "thread_count": threading.active_count(),
        "disk_free_bytes": max(0, disk.free),
        "disk_total_bytes": max(0, disk.total),
    }
    if usage is not None:
        maximum_rss = max(0, int(usage.ru_maxrss))
        if sys.platform != "darwin":
            maximum_rss *= 1024
        sample["peak_rss_bytes"] = maximum_rss
        sample["cpu_user_seconds"] = max(0.0, usage.ru_utime)
        sample["cpu_system_seconds"] = max(0.0, usage.ru_stime)
    open_fd_count = _open_fd_count()
    if open_fd_count is not None:
        sample["open_fd_count"] = open_fd_count
    return sample


def _open_fd_count() -> Optional[int]:
    for directory in (Path("/proc/self/fd"), Path("/dev/fd")):
        try:
            return sum(1 for _item in directory.iterdir())
        except OSError:
            continue
    return None


def _rotate_at_start(path: Path, *, max_bytes: int, backup_count: int) -> None:
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        for index in range(backup_count, 0, -1):
            source = path if index == 1 else path.with_name(f"{path.name}.{index - 1}")
            target = path.with_name(f"{path.name}.{index}")
            if not source.exists():
                continue
            if target.exists():
                target.unlink()
            source.replace(target)
    except OSError:
        # Fatal-signal capture is supplemental and must not break Core startup.
        return


__all__ = (
    "DEFAULT_LOG_BACKUP_COUNT",
    "DEFAULT_LOG_MAX_BYTES",
    "DEFAULT_RESOURCE_SAMPLE_SECONDS",
    "ProcessDiagnostics",
    "redact_diagnostic_text",
    "sample_process_resources",
)
