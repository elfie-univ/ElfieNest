"""Bounded background runner for the core-model validation scheduler."""

from __future__ import annotations

import threading
from typing import Callable


class CoreValidationWorker:
    """Run one injected core-validation pass without blocking service startup."""

    def __init__(
        self,
        run_pass: Callable[[], object],
        *,
        interval_seconds: float = 60.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._run_pass = run_pass
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        """Start one daemon worker; repeated calls do not create more workers."""
        with self._lock:
            if self.is_running:
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="ElfieNest-Core-Validation",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        """Request shutdown and wait only for the bounded current pass."""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_seconds)
        if thread is not None and not thread.is_alive():
            with self._lock:
                if self._thread is thread:
                    self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_pass()
            except (OSError, RuntimeError, TimeoutError, ValueError):
                # A single stale Provider/configuration observation must not
                # kill the Core worker. The next bounded pass can retry it.
                pass
            self._stop.wait(self._interval_seconds)


__all__ = ("CoreValidationWorker",)
