#!/usr/bin/env python3
"""ElfieNest backend service — FastAPI + engine background thread + DB-driven dynamic Elfie loading.

Startup flow:
    1. Initialize DB + seed Owner account
    2. Engine background thread: cognition Runtime → ElfieNestEngine
    3. Load final Elfie records → instantiate Elfie → register to engine
    4. Create FastAPI app → uvicorn blocks main thread

Command-line arguments:
    --port          HTTP port (default 8000)
    --godot-ws-port Godot WebSocket port (default 8765)
    --force         Compatibility flag; port occupants are never terminated by lookup

CLI tools:
    .venv/bin/python scripts/elfienest.py config    Open config TUI
    .venv/bin/python scripts/elfienest.py owner     Manage Owner account
    .venv/bin/python scripts/elfienest.py doctor    Run local diagnostics
    .venv/bin/python scripts/elfienest.py status    View service status
    .venv/bin/python scripts/elfienest.py restart   Restart service
    .venv/bin/python scripts/elfienest.py stop      Stop service
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import logging
import os
import secrets
import signal
import sys
import threading
import time
from pathlib import Path
from types import FrameType
from typing import Any, Callable, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ElfieNest backend service")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port (default 8000)",
    )
    parser.add_argument(
        "--godot-ws-port",
        type=int,
        default=None,
        help="Godot WebSocket port (default 8765)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compatibility flag; never terminates a port occupant",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Listen on LAN IPv4 address explicitly (default: localhost only)",
    )
    parser.add_argument(
        "--runtime-mode",
        choices=("development", "release"),
        default=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        help="Godot Web Runtime lifecycle mode (default: development)",
    )
    parser.add_argument(
        "--data-home",
        default=None,
        help="Use an explicit ElfieNest data root for this serve process",
    )
    return parser


def _delegate_direct_source_invocation() -> None:
    """Route manual source-Core launches through the same lifecycle authority.

    ``scripts/serve.py`` is the managed Core entrypoint.  When a developer
    invokes it directly, there is no parent Supervisor to reserve a
    generation or publish ``CORE_READY``.  Re-enter the public foreground
    command instead; the Supervisor will launch this file again with the
    managed-start marker and the second invocation continues as Core.
    """
    if os.environ.get("ELFIENEST_MANAGED_START") == "1":
        return
    if getattr(sys, "frozen", False):
        raise SystemExit(
            "ElfieNestCore must be started by the installed management CLI"
        )
    for index, argument in enumerate(sys.argv[1:]):
        if argument == "--runtime-mode" and index + 2 <= len(sys.argv[1:]):
            os.environ["ELFIENEST_RUNTIME_MODE"] = sys.argv[index + 2]
            break
        if argument.startswith("--runtime-mode="):
            os.environ["ELFIENEST_RUNTIME_MODE"] = argument.split("=", 1)[1]
            break
    cli_entrypoint = Path(__file__).resolve().with_name("elfienest.py")
    os.execv(
        sys.executable,
        [sys.executable, str(cli_entrypoint), "serve", *sys.argv[1:]],
    )


# Reject invalid arguments before importing the service composition graph.  This
# keeps help and parser errors responsive even when the full Runtime is expensive
# to import on a cold Python process.
if __name__ == "__main__":
    _build_argument_parser().parse_args()
    _delegate_direct_source_invocation()

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from app.bootstrap import (
    ProcessDiagnosticsHandle,
    create_app,
    open_core_process_diagnostics,
)
from app.bootstrap.app_wiring.accounts import build_accounts_service
from app.bootstrap.app_wiring.storage import ensure_application_storage
from app.bootstrap.model_execution import (
    ModelExecutionServices,
    build_model_execution_services,
)
from app.bootstrap.system_wiring.entrypoints import (
    DataHomeSelectionError,
    get_db_path,
    get_elfie_home,
    inspect_godot_web_bundle,
    select_elfie_home,
)
from app.bootstrap.system_wiring.lifecycle import (
    create_lifecycle_facade,
    create_runtime_capability_gate,
    runtime_projection_payload,
)
from app.bootstrap.system_wiring.nest_session import (
    bind_service_endpoints,
    build_nest_session_services,
    load_emotion_expression_config,
    restore_registered_elfies,
)
from app.features.accounts import SeedInitialOwnerCommand
from app.interfaces.api.service_access import ServiceMode
from app.orchestration.lifecycle import (
    DEFAULT_GODOT_WS_PORT,
    DEFAULT_HTTP_PORT,
    MANAGED_START_ENV,
    AuthorityHostConfig,
    EndpointSnapshot,
    FrontendPreparationError,
    RecoveryInProgressError,
    validate_service_ports,
)

WORLD_CONVERGENCE_TIMEOUT_SECONDS = 120.0
ENGINE_STALL_MINIMUM_SECONDS = 120.0
ENGINE_STALL_INTERVAL_MULTIPLIER = 20.0
ENGINE_STALL_CONFIRMATION_SECONDS = 30.0
ENGINE_PROGRESS_HEARTBEAT_SECONDS = 300.0
ENGINE_MONITOR_POLL_SECONDS = 1.0
cleanup_logger = logging.getLogger("elfienest.diagnostics.core_cleanup")


class EngineStalledError(RuntimeError):
    """The production Engine stopped completing its non-blocking clock tick."""


class EngineFailureSignal:
    """Publish the first fatal Engine result across process-local threads."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._error: BaseException | None = None

    @property
    def error(self) -> BaseException | None:
        with self._lock:
            return self._error

    def fail(self, error: BaseException) -> bool:
        with self._lock:
            if self._error is not None:
                return False
            self._error = error
            self._event.set()
            return True

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


def _diagnostic_event(
    diagnostics: ProcessDiagnosticsHandle | None,
    event: str,
    *,
    level: int = logging.INFO,
    message: str = "",
    **fields: object,
) -> None:
    if diagnostics is None:
        return
    try:
        diagnostics.event(event, level=level, message=message, **fields)
    except (OSError, RuntimeError, ValueError):
        # Supplemental observability may never become a new Core failure.
        return


def _diagnostic_exception(
    diagnostics: ProcessDiagnosticsHandle | None,
    event: str,
    error: BaseException,
    *,
    level: int = logging.ERROR,
    **fields: object,
) -> None:
    if diagnostics is None:
        return
    try:
        diagnostics.exception(event, error, level=level, **fields)
    except (OSError, RuntimeError, ValueError):
        return


def _open_core_diagnostics(elfie_home: Path) -> ProcessDiagnosticsHandle | None:
    try:
        return open_core_process_diagnostics(
            elfie_home,
            source_revision=os.environ.get("ELFIENEST_SOURCE_REVISION"),
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(
            "  ⚠️ Structured Core diagnostics unavailable "
            f"({type(error).__name__}); continuing with managed console output"
        )
        return None


def _close_diagnostics_safely(diagnostics: ProcessDiagnosticsHandle) -> None:
    try:
        diagnostics.close()
    except (OSError, RuntimeError, ValueError):
        return


def _install_managed_core_sigterm_handler(
    diagnostics: ProcessDiagnosticsHandle | None,
) -> Callable[[], None]:
    """Let Uvicorn re-raise managed SIGTERM without skipping Core cleanup."""
    previous_handler = signal.getsignal(signal.SIGTERM)
    recorded = False

    def handle_sigterm(signum: int, _frame: FrameType | None) -> None:
        nonlocal recorded
        if recorded:
            return
        recorded = True
        _diagnostic_event(
            diagnostics,
            "core_shutdown_requested",
            phase="core_stopping",
            signal=signal.Signals(signum).name,
            status="requested",
        )

    signal.signal(signal.SIGTERM, handle_sigterm)

    def restore() -> None:
        if signal.getsignal(signal.SIGTERM) is handle_sigterm:
            signal.signal(signal.SIGTERM, previous_handler)

    return restore


def monitor_engine_progress(
    engine: Any,
    failure: EngineFailureSignal,
    shutdown_requested: threading.Event,
    diagnostics: ProcessDiagnosticsHandle | None,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    poll_seconds: float = ENGINE_MONITOR_POLL_SECONDS,
    confirmation_seconds: float = ENGINE_STALL_CONFIRMATION_SECONDS,
    heartbeat_seconds: float = ENGINE_PROGRESS_HEARTBEAT_SECONDS,
    stall_threshold_seconds: float | None = None,
) -> None:
    """Observe Engine progress and publish a confirmed stall as one Core fatal."""
    stall_threshold = (
        max(
            ENGINE_STALL_MINIMUM_SECONDS,
            ENGINE_STALL_INTERVAL_MULTIPLIER * max(0.0, engine.tick_interval_sec),
        )
        if stall_threshold_seconds is None
        else max(0.0, stall_threshold_seconds)
    )
    next_heartbeat = monotonic()
    suspected_tick: int | None = None
    suspected_at: float | None = None
    while not shutdown_requested.wait(max(0.001, poll_seconds)):
        if failure.is_set():
            return
        if not engine.is_running:
            if engine.stop_requested:
                return
            error = RuntimeError(
                "production Engine loop stopped without a stop request"
            )
            if failure.fail(error):
                _diagnostic_exception(
                    diagnostics,
                    "engine_loop_stopped_unexpectedly",
                    error,
                    phase="core_ready",
                )
            return

        now = monotonic()
        progress = engine.progress_snapshot()
        age = engine.progress_age_seconds(now=now)
        if now >= next_heartbeat:
            _diagnostic_event(
                diagnostics,
                "engine_progress",
                completed_ticks=progress.completed_ticks,
                last_progress_age_ms=(None if age is None else max(0, int(age * 1000))),
                last_tick_duration_ms=(
                    None
                    if progress.last_tick_duration_seconds is None
                    else max(0, int(progress.last_tick_duration_seconds * 1000))
                ),
                phase="core_ready",
            )
            next_heartbeat = now + max(1.0, heartbeat_seconds)

        if age is None or age < stall_threshold:
            suspected_tick = None
            suspected_at = None
            continue
        if suspected_tick != progress.completed_ticks:
            suspected_tick = progress.completed_ticks
            suspected_at = now
            _diagnostic_event(
                diagnostics,
                "engine_stall_suspected",
                level=logging.WARNING,
                completed_ticks=progress.completed_ticks,
                last_progress_age_ms=max(0, int(age * 1000)),
                phase="core_ready",
            )
            if diagnostics is not None:
                try:
                    diagnostics.dump_all_thread_traces(reason="engine_stall_suspected")
                except (OSError, RuntimeError, ValueError):
                    pass
            continue
        assert suspected_at is not None
        if now - suspected_at < max(0.0, confirmation_seconds):
            continue
        confirmed = engine.progress_snapshot()
        if confirmed.completed_ticks != suspected_tick:
            suspected_tick = None
            suspected_at = None
            continue
        error = EngineStalledError(
            "production Engine did not complete a tick within its stall budget"
        )
        if failure.fail(error):
            _diagnostic_exception(
                diagnostics,
                "engine_stalled_fatal",
                error,
                phase="core_ready",
                completed_ticks=confirmed.completed_ticks,
                last_progress_age_ms=max(0, int((age or 0.0) * 1000)),
            )
        return


def stop_server_on_engine_failure(
    failure: EngineFailureSignal,
    shutdown_requested: threading.Event,
    server: Any,
) -> None:
    """Ask Uvicorn to quiesce only after the Engine guard publishes a fatal."""
    while not shutdown_requested.is_set():
        if failure.wait(0.1):
            if not shutdown_requested.is_set():
                server.should_exit = True
            return


class RuntimeStartupCleanup:
    """Own every resource acquired after a Core receipt is published.

    The foreground Core can fail before Uvicorn enters its normal ``finally``
    block.  Registering this guard immediately after receipt registration
    makes those failures converge through the same reverse-order cleanup as a
    normal stop.  Managed starts leave the PID receipt to their parent
    Supervisor; foreground starts remove only their own receipt.
    """

    def __init__(self, lifecycle, elfie_home: Path, *, managed_start: bool) -> None:
        self.lifecycle = lifecycle
        self.elfie_home = elfie_home
        self.receipt_owned = not managed_start
        self.receipt_registered = False
        self.world_worker: Any = None
        self.world_runtime: Any = None
        self.optional_lease: Any = None
        self.optional_lease_thread: threading.Thread | None = None
        self.optional_lease_stop = threading.Event()
        self.monitor_stop = threading.Event()
        self.monitor_threads: list[threading.Thread] = []
        self.engine_thread: threading.Thread | None = None
        self.engine: Any = None
        self.godot_build_thread: threading.Thread | None = None
        self.endpoint_sockets: Any = None
        self._cleaned = False

    def cleanup(self) -> None:
        """Release World, model lease, Runtime channel and owned receipt once."""
        if self._cleaned:
            return
        self._cleaned = True
        self.optional_lease_stop.set()
        self.monitor_stop.set()

        if self.engine is not None:
            try:
                self.engine.request_stop()
            except (RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "Engine stop request failed",
                    extra={
                        "diagnostic_event": "engine_stop_request_failed",
                        "component": "engine",
                    },
                )
                print(f"  ⚠️ Engine stop request failed: {error}")

        if self.world_worker is not None:
            try:
                detail = self.world_worker.stop()
                if detail:
                    cleanup_logger.error(
                        "World cleanup incomplete: %s",
                        detail,
                        extra={
                            "diagnostic_event": "world_cleanup_incomplete",
                            "component": "world_worker",
                        },
                    )
                    print(f"  ⚠️ World cleanup incomplete: {detail}")
            except (OSError, RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "World cleanup failed",
                    extra={
                        "diagnostic_event": "world_cleanup_failed",
                        "component": "world_worker",
                    },
                )
                print(f"  ⚠️ World cleanup failed: {error}")

        if self.optional_lease_thread is not None:
            self._join_thread(self.optional_lease_thread, "optional_model_lease")
        lease = self.optional_lease
        self.optional_lease = None
        if lease is not None:
            try:
                lease.release()
            except (OSError, RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "Local model lease release failed",
                    extra={
                        "diagnostic_event": "optional_lease_cleanup_failed",
                        "component": "optional_model_lease",
                    },
                )
                print(f"  ⚠️ Local Ollama release incomplete: {error}")

        if self.world_runtime is not None:
            try:
                self.lifecycle.stop_runtime_channel(self.world_runtime)
            except (OSError, RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "Runtime channel cleanup failed",
                    extra={
                        "diagnostic_event": "runtime_channel_cleanup_failed",
                        "component": "runtime_channel",
                    },
                )
                print(f"  ⚠️ Runtime channel cleanup failed: {error}")

        if (
            self.engine_thread is not None
            and self.engine_thread is not threading.current_thread()
        ):
            self._join_thread(self.engine_thread, "engine")
        if (
            self.godot_build_thread is not None
            and self.godot_build_thread is not threading.current_thread()
        ):
            self._join_thread(self.godot_build_thread, "godot_web_build")
        for monitor_thread in self.monitor_threads:
            if monitor_thread is not threading.current_thread():
                self._join_thread(monitor_thread, monitor_thread.name)

        if self.endpoint_sockets is not None:
            try:
                self.endpoint_sockets.close()
            except (OSError, RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "Endpoint socket cleanup failed",
                    extra={
                        "diagnostic_event": "endpoint_socket_cleanup_failed",
                        "component": "endpoint_sockets",
                    },
                )
                print(f"  ⚠️ Endpoint socket cleanup failed: {error}")
            finally:
                self.endpoint_sockets = None

        if self.receipt_registered and self.receipt_owned:
            try:
                self.lifecycle.clear_receipt(self.elfie_home)
            except (OSError, RuntimeError, ValueError) as error:
                cleanup_logger.exception(
                    "Service receipt cleanup failed",
                    extra={
                        "diagnostic_event": "service_receipt_cleanup_failed",
                        "component": "service_receipt",
                    },
                )
                print(f"  ⚠️ Service receipt cleanup failed: {error}")

    @staticmethod
    def _join_thread(thread: threading.Thread, component: str) -> None:
        try:
            thread.join(timeout=1.0)
        except RuntimeError:
            # ``Thread.start`` may fail after the cleanup guard has claimed
            # the object; an unstarted thread has no resource to wait for.
            cleanup_logger.exception(
                "Background thread could not be joined",
                extra={
                    "diagnostic_event": "background_thread_join_failed",
                    "component": component,
                },
            )
            return
        is_alive = getattr(thread, "is_alive", None)
        if callable(is_alive) and is_alive():
            cleanup_logger.error(
                "Background thread did not stop within 1.0s",
                extra={
                    "diagnostic_event": "background_thread_stop_timeout",
                    "component": component,
                },
            )


def _finalize_core_runtime(
    startup_cleanup: RuntimeStartupCleanup,
    diagnostics: ProcessDiagnosticsHandle | None,
    *,
    fatal_exit: bool,
) -> None:
    """Bracket managed cleanup with durable process-terminal diagnostics."""
    _diagnostic_event(
        diagnostics,
        "core_process_stopping",
        phase="core_stopping",
        status="failed" if fatal_exit else "stopping",
    )
    startup_cleanup.cleanup()
    _diagnostic_event(
        diagnostics,
        "core_process_stopped",
        phase="core_stopping",
        status="failed" if fatal_exit else "stopped",
    )


def remaining_occupied_ports(
    occupied: Sequence[tuple[int, str]],
    is_port_in_use_func: Callable[[int], bool],
) -> list[tuple[int, str]]:
    """Return ports that remain occupied after force cleanup."""
    return [(port, name) for port, name in occupied if is_port_in_use_func(port)]


def select_implicit_service_ports(
    lifecycle,
    data_home: Path,
    *,
    http_port: int | None,
    godot_ws_port: int | None,
) -> tuple[int, int]:
    """Move only implicit defaults away from unrelated local occupants."""
    selected_http = DEFAULT_HTTP_PORT if http_port is None else http_port
    selected_ws = DEFAULT_GODOT_WS_PORT if godot_ws_port is None else godot_ws_port
    if http_port is not None or godot_ws_port is not None:
        return selected_http, selected_ws
    try:
        occupied = lifecycle.ports_in_use((selected_http, selected_ws))
    except OSError:
        return selected_http, selected_ws
    if not occupied:
        return selected_http, selected_ws
    try:
        if (
            lifecycle.existing_service_command(
                data_home,
                Path(__file__).resolve().parent.parent,
            )
            is not None
        ):
            return selected_http, selected_ws
    except OSError:
        return selected_http, selected_ws
    digest = hashlib.sha256(str(data_home.resolve()).encode("utf-8")).digest()
    start = 12000 + int.from_bytes(digest[:2], "big") % 12000
    for offset in range(0, 2000, 2):
        candidate_http = start + offset
        candidate_ws = candidate_http + 1
        if candidate_ws > 65535:
            break
        try:
            if not lifecycle.ports_in_use((candidate_http, candidate_ws)):
                return candidate_http, candidate_ws
        except OSError:
            return selected_http, selected_ws
    return selected_http, selected_ws


def service_host(lan: bool) -> str:
    """Keep developer CLI loopback-only unless the caller explicitly enables LAN."""
    return "0.0.0.0" if lan else "127.0.0.1"


def prepare_godot_web_runtime(
    lifecycle,
    runtime_mode: str,
    is_frozen: bool = bool(getattr(sys, "frozen", False)),
) -> bool:
    """Ensure or validate Godot Web Runtime for the selected mode, returning availability."""
    return lifecycle.prepare_godot_web(runtime_mode, is_frozen=is_frozen)


def prepare_frontend_web_runtime(
    lifecycle,
    runtime_mode: str,
) -> None:
    """Ensure the source Web client is current before a development launch."""
    if runtime_mode == "development":
        lifecycle.prepare_frontend(runtime_mode)


def register_service_process_for_start(
    lifecycle, elfie_home: Path, *, managed_start: bool
) -> None:
    """Let the parent Supervisor own managed receipts, including frozen Core parents."""
    if not managed_start:
        lifecycle.register_current_service(elfie_home)


def _configure_console_encoding() -> None:
    """Keep Unicode startup diagnostics from crashing on Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # A closed or non-standard stream should not prevent service startup.
            continue


def build_server_model_execution_services(db_path: str) -> ModelExecutionServices:
    """Build model services without issuing a startup inference request."""
    return build_model_execution_services(
        db_path,
        live_reload=True,
        resolve_main_food=True,
    )


def main():
    _configure_console_encoding()
    os.environ["ELFIENEST_PROCESS_ROLE"] = "core"
    parser = _build_argument_parser()
    args = parser.parse_args()
    lifecycle = create_lifecycle_facade()
    explicit_http_port = args.port
    explicit_godot_ws_port = args.godot_ws_port
    if args.godot_ws_port is None:
        args.godot_ws_port = DEFAULT_GODOT_WS_PORT

    godot_nonce = os.environ.get("ELFIENEST_GODOT_NONCE", "").strip()
    if not godot_nonce:
        godot_nonce = secrets.token_urlsafe(32)
        os.environ["ELFIENEST_GODOT_NONCE"] = godot_nonce

    try:
        select_elfie_home(
            args.data_home,
            invoking_cwd=Path.cwd(),
            runtime_mode=args.runtime_mode,
            source_root=Path(__file__).resolve().parent.parent,
        )
    except DataHomeSelectionError as error:
        parser.error(str(error))

    diagnostics = _open_core_diagnostics(get_elfie_home())
    _diagnostic_event(diagnostics, "core_process_started", phase="preflight")
    if diagnostics is not None:
        atexit.register(_close_diagnostics_safely, diagnostics)

    args.port, args.godot_ws_port = select_implicit_service_ports(
        lifecycle,
        get_elfie_home(),
        http_port=explicit_http_port,
        godot_ws_port=explicit_godot_ws_port,
    )

    port_error = validate_service_ports(
        args.port,
        args.godot_ws_port,
    )
    if port_error:
        parser.error(port_error)

    try:
        prepare_frontend_web_runtime(lifecycle, args.runtime_mode)
    except FrontendPreparationError as error:
        print(f"  ❌ Frontend Web build failed: {error}")
        raise SystemExit(1) from None

    managed_start = os.environ.pop(MANAGED_START_ENV, "") == "1"
    try:
        start_lease = lifecycle.acquire_start_lease(
            get_elfie_home(), blocking=managed_start
        )
    except (OSError, RecoveryInProgressError):
        print(
            "  ❌ Owner account recovery or another service start in progress, cannot start"
        )
        raise SystemExit(1) from None

    godot_ready = prepare_godot_web_runtime(lifecycle, args.runtime_mode)
    if args.runtime_mode == "release" and not godot_ready:
        print(
            "  ❌ Release mode requires verified Godot Web Runtime, service not started"
        )
        raise SystemExit(1)

    godot_web = inspect_godot_web_bundle()
    if godot_ready and godot_web.ready:
        print(f"  ✅ Godot Web Runtime: {godot_web.entry_url}")
    else:
        print("  ⚠️  Godot Web Runtime unavailable or stale; 3D room unavailable")
        print(
            "  💡 Run after modifying Godot assets or before release: "
            "./developer.sh build-godot-web --ensure"
        )

    startup_cleanup = RuntimeStartupCleanup(
        lifecycle,
        get_elfie_home(),
        managed_start=managed_start,
    )
    startup_cleanup.receipt_registered = not managed_start
    atexit.register(startup_cleanup.cleanup)
    try:
        register_service_process_for_start(
            lifecycle,
            get_elfie_home(),
            managed_start=managed_start,
        )
    except OSError as error:
        startup_cleanup.cleanup()
        start_lease.release()
        print(f"  ❌ Cannot register service process: {error}")
        raise SystemExit(1) from None
    start_lease.release()
    if diagnostics is not None:
        try:
            runtime_identity = lifecycle.runtime_snapshot(get_elfie_home())
            diagnostics.bind_runtime_context(
                instance_id=runtime_identity.instance_id,
                generation=runtime_identity.generation,
                correlation_id=runtime_identity.correlation_id,
            )
        except (OSError, RuntimeError, ValueError) as error:
            _diagnostic_exception(
                diagnostics,
                "runtime_diagnostic_context_unavailable",
                error,
                level=logging.WARNING,
                phase="preflight",
            )

    automatic_ports = explicit_http_port is None and explicit_godot_ws_port is None
    try:
        bound_endpoints = bind_service_endpoints(
            args.port,
            args.godot_ws_port,
            automatic=automatic_ports,
            host=service_host(args.lan),
        )
        startup_cleanup.endpoint_sockets = bound_endpoints
        args.port = bound_endpoints.http_port
        args.godot_ws_port = bound_endpoints.websocket_port
        lifecycle.publish_core_endpoints(
            get_elfie_home(),
            (
                EndpointSnapshot("http", "http", service_host(args.lan), args.port),
                EndpointSnapshot(
                    "godot_ws", "ws", service_host(args.lan), args.godot_ws_port
                ),
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        startup_cleanup.cleanup()
        print(f"  ❌ Cannot reserve Runtime endpoints: {error}")
        raise SystemExit(1) from None
    db_path = str(get_db_path())

    # 1. Initialize the final database and invoke the explicit Owner seed use-case.
    ensure_application_storage(db_path)
    build_accounts_service(db_path).seed_initial_owner(SeedInitialOwnerCommand())

    # 2. Verify model execution before accepting chat messages.
    model_execution_services = build_server_model_execution_services(db_path)

    # 3. Start the engine worker thread.
    engine_holder: dict[str, Any] = {}
    engine_failure = EngineFailureSignal()
    engine_constructed = threading.Event()

    def engine_worker():
        engine: Any = None
        try:
            nest_session = build_nest_session_services(
                db_path,
                model_execution=model_execution_services.execution,
                godot_ws_port=args.godot_ws_port,
                http_port=args.port,
                tick_interval_sec=model_execution_services.tick_interval_sec,
                godot_socket=bound_endpoints.websocket,
                main_food_loader=model_execution_services.main_food_loader,
            )
            startup_cleanup.world_runtime = nest_session.world_runtime
            lifecycle.start_runtime_channel(nest_session.world_runtime)
            engine = nest_session.engine
            engine_holder["engine"] = engine
            engine_holder["world_runtime"] = nest_session.world_runtime
            startup_cleanup.engine = engine
            engine_constructed.set()
            _diagnostic_event(
                diagnostics,
                "engine_loop_starting",
                phase="core_starting",
            )
            engine.start_loop(
                model_port_factory=nest_session.model_port_factory,
                ticks_to_run=None,
            )
            if not engine.stop_requested and not startup_cleanup.monitor_stop.is_set():
                error = RuntimeError(
                    "production Engine loop returned without a stop request"
                )
                if engine_failure.fail(error):
                    _diagnostic_exception(
                        diagnostics,
                        "engine_loop_stopped_unexpectedly",
                        error,
                        phase="core_ready",
                    )
        except BaseException as error:
            expected_shutdown = startup_cleanup.monitor_stop.is_set() or (
                engine is not None and engine.stop_requested
            )
            if expected_shutdown:
                _diagnostic_exception(
                    diagnostics,
                    "engine_shutdown_failed",
                    error,
                    level=logging.WARNING,
                    phase="core_stopping",
                )
            elif engine_failure.fail(error):
                _diagnostic_exception(
                    diagnostics,
                    "engine_loop_failed",
                    error,
                    phase="core",
                )
        finally:
            engine_constructed.set()
            _diagnostic_event(
                diagnostics,
                "engine_loop_stopped",
                phase="core",
                status="failed" if engine_failure.is_set() else "stopped",
            )

    engine_thread = threading.Thread(
        target=engine_worker,
        name="ElfieNest-Engine",
        daemon=True,
    )
    startup_cleanup.engine_thread = engine_thread
    engine_thread.start()

    startup_deadline = time.monotonic() + 5.0
    engine_constructed.wait(timeout=5.0)
    if "engine" not in engine_holder:
        engine_error = engine_failure.error
        if engine_error is None:
            _diagnostic_event(
                diagnostics,
                "engine_start_failed",
                level=logging.ERROR,
                message="engine construction did not complete within 5 seconds",
                phase="core_starting",
            )
            print("❌ Engine failed to become ready within 5s")
        else:
            print(f"❌ Engine failed to become ready: {engine_error}")
        sys.exit(1)
    engine = engine_holder["engine"]
    remaining_startup_time = max(0.0, startup_deadline - time.monotonic())
    if not engine.wait_until_running(timeout=remaining_startup_time):
        engine_error = engine_failure.error
        if engine_error is None:
            _diagnostic_event(
                diagnostics,
                "engine_start_failed",
                level=logging.ERROR,
                message="engine loop did not enter the running state within 5 seconds",
                phase="core_starting",
            )
            print("❌ Engine failed to enter its running state within 5s")
        else:
            print(f"❌ Engine failed to become ready: {engine_error}")
        sys.exit(1)
    _diagnostic_event(diagnostics, "engine_loop_ready", phase="core_ready")
    engine_watchdog = threading.Thread(
        target=monitor_engine_progress,
        args=(
            engine,
            engine_failure,
            startup_cleanup.monitor_stop,
            diagnostics,
        ),
        name="ElfieNest-Engine-Watchdog",
        daemon=True,
    )
    startup_cleanup.monitor_threads.append(engine_watchdog)
    engine_watchdog.start()
    print("  ℹ️ Godot Web Runtime is hosted by ElfieNest Desktop hidden window")

    # 4. Dynamically load all Elfies from the database.
    loaded_elfies: list[dict] = []
    try:
        restore_result = restore_registered_elfies(
            db_path,
            engine.session,
            emotion_expression_config=load_emotion_expression_config(),
        )
        loaded_elfies = [
            {"id": item.elfie_id, "name": item.name} for item in restore_result.restored
        ]
        for failure in restore_result.failures:
            print(
                f"  ⚠️  Failed to load Elfie {failure.name} "
                f"({failure.elfie_id}) failed: {failure.error}"
            )
    except Exception as e:
        print(f"  ⚠️  Failed to query Elfie list: {e}")

    world_worker = lifecycle.runtime_world_worker(
        elfie_home=get_elfie_home(),
        authority_config=AuthorityHostConfig(
            project_root=Path(__file__).resolve().parent.parent,
            http_port=args.port,
            ws_port=args.godot_ws_port,
            nonce=godot_nonce,
            core_pid_file=get_elfie_home() / "elfienest.pid",
        ),
        world_ready_probe=lambda: bool(engine.session.runtime_world_ready),
        authority_timeout_seconds=WORLD_CONVERGENCE_TIMEOUT_SECONDS,
    )
    startup_cleanup.world_worker = world_worker
    world_worker.start()

    godot_build_thread: threading.Thread | None = None
    if args.runtime_mode == "development" and not godot_ready:

        def prepare_godot_in_background() -> None:
            try:
                if prepare_godot_web_runtime(lifecycle, args.runtime_mode):
                    print("  ✅ Godot Web Runtime prepared in background")
                else:
                    print(
                        "  ⚠️  Godot Web Runtime preparation failed; 3D preview remains unavailable"
                    )
            except (
                OSError,
                RuntimeError,
                ValueError,
                FrontendPreparationError,
            ) as error:
                _diagnostic_exception(
                    diagnostics,
                    "godot_web_prepare_failed",
                    error,
                )
                print(f"  ⚠️  Godot Web Runtime preparation failed: {error}")

        godot_build_thread = threading.Thread(
            target=prepare_godot_in_background,
            name="ElfieNest-Godot-Web-Preparation",
            daemon=True,
        )
        startup_cleanup.godot_build_thread = godot_build_thread
        godot_build_thread.start()

    optional_lease_stop = startup_cleanup.optional_lease_stop

    def acquire_optional_lease() -> None:
        try:
            snapshot = lifecycle.runtime_snapshot(get_elfie_home())
            lease = lifecycle.acquire_optional_component_lease(
                owner_id=f"core:{os.getpid()}",
                instance_id=snapshot.instance_id,
                generation=snapshot.generation,
                elfie_home=get_elfie_home(),
            )
            if lease is None:
                return
            if optional_lease_stop.is_set():
                lease.release()
                return
            startup_cleanup.optional_lease = lease
        except (OSError, RuntimeError, ValueError) as error:
            _diagnostic_exception(
                diagnostics,
                "optional_component_lease_failed",
                error,
            )
            print(f"  ⚠️ Local Ollama did not converge: {error}")

    optional_lease_thread = threading.Thread(
        target=acquire_optional_lease,
        name="ElfieNest-Ollama-Lease",
        daemon=True,
    )
    startup_cleanup.optional_lease_thread = optional_lease_thread
    optional_lease_thread.start()

    # 5. Print startup information.
    print()
    print("=" * 56)
    print("  🦊 ElfieNest Embodied AI Creature Service")
    print("=" * 56)
    print(f"  🌐 HTTP:    http://127.0.0.1:{args.port}")
    print(f"  🔌 WebSocket(Godot): ws://127.0.0.1:{args.godot_ws_port}")
    if loaded_elfies:
        names_str = ", ".join(e["name"] for e in loaded_elfies)
        print(f"  ✨ Loaded {len(loaded_elfies)}  Elfie(s): {names_str}")
    else:
        print("  ✨ No Elfie loaded (adopt one after login)")
    print()
    print(f"  📖 Open in browser: http://127.0.0.1:{args.port}/")
    print("  ⌨️  Press Ctrl+C to stop")
    print("=" * 56)
    print()

    # 6. Create the FastAPI app and start uvicorn on the main thread.
    app = create_app(
        engine=engine,
        db_path=db_path,
        http_port=args.port,
        service_mode=ServiceMode.LAN.value if args.lan else ServiceMode.LOOPBACK.value,
        model_execution=model_execution_services.execution,
        runtime_capability_gate=create_runtime_capability_gate(
            lifecycle, get_elfie_home()
        ),
        runtime_projection=lambda: runtime_projection_payload(
            lifecycle, get_elfie_home()
        ),
        diagnostics=diagnostics,
    )

    import uvicorn  # noqa: PLC0415

    restore_sigterm_handler = _install_managed_core_sigterm_handler(diagnostics)
    fatal_exit = False
    try:
        config = uvicorn.Config(
            app,
            host=service_host(args.lan),
            limit_concurrency=100,
            port=args.port,
            log_config=None,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        engine_failure_monitor = threading.Thread(
            target=stop_server_on_engine_failure,
            args=(engine_failure, startup_cleanup.monitor_stop, server),
            name="ElfieNest-Engine-Failure-Bridge",
            daemon=True,
        )
        startup_cleanup.monitor_threads.append(engine_failure_monitor)
        engine_failure_monitor.start()
        if engine_failure.is_set():
            server.should_exit = True
        _diagnostic_event(diagnostics, "core_http_serving", phase="core_ready")
        server.run(sockets=[bound_endpoints.http])
        fatal_exit = engine_failure.is_set()
    except KeyboardInterrupt:
        print("\nShutting down service...")
    except BaseException as error:
        fatal_exit = True
        _diagnostic_exception(
            diagnostics,
            "core_http_server_failed",
            error,
            level=logging.CRITICAL,
            phase="core_ready",
        )
        raise
    finally:
        fatal_exit = fatal_exit or engine_failure.is_set()
        startup_cleanup.monitor_stop.set()
        try:
            _finalize_core_runtime(
                startup_cleanup,
                diagnostics,
                fatal_exit=fatal_exit,
            )
        finally:
            restore_sigterm_handler()
        print("Service stopped.")
    if fatal_exit:
        engine_error = engine_failure.error
        print(
            "❌ Core stopped because the Engine became unhealthy"
            + ("" if engine_error is None else f": {type(engine_error).__name__}")
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
