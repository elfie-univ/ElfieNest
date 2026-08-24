"""Production composition for process-level diagnostics."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Protocol

from infrastructure.platform.diagnostics import ProcessDiagnostics


class ProcessDiagnosticsHandle(Protocol):
    """Narrow process-diagnostics surface exposed to production entrypoints."""

    def event(
        self,
        event: str,
        *,
        level: int,
        message: str,
        **fields: object,
    ) -> None: ...

    def exception(
        self,
        event: str,
        error: BaseException,
        *,
        level: int,
        **fields: object,
    ) -> None: ...

    def bind_runtime_context(
        self,
        *,
        instance_id: str,
        generation: int,
        correlation_id: str | None = None,
    ) -> None: ...

    def dump_all_thread_traces(self, *, reason: str) -> bool: ...

    def install_asyncio_exception_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> Callable[[], None]: ...

    def close(self) -> None: ...


def open_core_process_diagnostics(
    elfie_home: Path,
    *,
    source_revision: str | None = None,
) -> ProcessDiagnosticsHandle:
    """Create and fully initialize the managed Core diagnostic sink."""
    diagnostics = ProcessDiagnostics(
        elfie_home,
        role="core",
        source_revision=source_revision,
    )
    try:
        diagnostics.configure_root_warning_log()
        diagnostics.install_exception_hooks()
        diagnostics.start_resource_monitor()
    except BaseException:
        try:
            diagnostics.close()
        except (OSError, RuntimeError, ValueError):
            pass
        raise
    return diagnostics


__all__ = (
    "ProcessDiagnosticsHandle",
    "open_core_process_diagnostics",
)
