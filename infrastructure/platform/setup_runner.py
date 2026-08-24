"""Process-local background Runner Adapter for Setup installation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Event, Lock, Thread, Timer
from typing import Callable

logger = logging.getLogger("infrastructure.platform.setup_runner")


@dataclass
class _RunningSetupTask:
    thread: Thread
    cancelled: Event
    timeout: Timer


class ThreadSetupInstallationRunner:
    """Run at most one Setup worker per injected installation key."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, _RunningSetupTask] = {}

    def start(
        self,
        key: str,
        worker: Callable[[Callable[[], bool]], None],
        *,
        timeout_seconds: float,
        on_timeout: Callable[[], None],
    ) -> bool:
        with self._lock:
            current = self._tasks.get(key)
            if current is not None and current.thread.is_alive():
                return False
            cancelled = Event()

            def timeout() -> None:
                cancelled.set()
                try:
                    on_timeout()
                except Exception:  # noqa: BLE001 - infrastructure callback boundary
                    logger.exception("Setup installation timeout callback failed")

            timeout_timer = Timer(timeout_seconds, timeout)
            timeout_timer.daemon = True

            def run() -> None:
                try:
                    worker(cancelled.is_set)
                finally:
                    timeout_timer.cancel()

            thread = Thread(
                target=run,
                name="elfienest-setup-install",
                daemon=True,
            )
            self._tasks[key] = _RunningSetupTask(thread, cancelled, timeout_timer)
            timeout_timer.start()
            thread.start()
            return True

    def cancel(self, key: str) -> bool:
        with self._lock:
            current = self._tasks.get(key)
            if current is None or not current.thread.is_alive():
                return False
            current.cancelled.set()
            current.timeout.cancel()
            return True

    def join(self, key: str, timeout: float) -> bool:
        with self._lock:
            task = self._tasks.get(key)
            current = None if task is None else task.thread
        if current is None:
            return True
        current.join(timeout=timeout)
        return not current.is_alive()


__all__ = ("ThreadSetupInstallationRunner",)
