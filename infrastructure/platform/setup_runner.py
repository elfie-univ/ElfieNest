"""Process-local background Runner Adapter for Setup installation."""

from __future__ import annotations

from threading import Lock, Thread
from typing import Callable


class ThreadSetupInstallationRunner:
    """Run at most one Setup worker per injected installation key."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._threads: dict[str, Thread] = {}

    def start(self, key: str, worker: Callable[[], None]) -> bool:
        with self._lock:
            current = self._threads.get(key)
            if current is not None and current.is_alive():
                return False
            thread = Thread(
                target=worker,
                name="elfienest-setup-install",
                daemon=True,
            )
            self._threads[key] = thread
            thread.start()
            return True

    def join(self, key: str, timeout: float) -> bool:
        with self._lock:
            current = self._threads.get(key)
        if current is None:
            return True
        current.join(timeout=timeout)
        return not current.is_alive()


__all__ = ("ThreadSetupInstallationRunner",)
