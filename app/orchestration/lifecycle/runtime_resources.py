"""Lifecycle owner for in-process managed Runtime resources."""

from __future__ import annotations

from threading import RLock
from typing import Protocol, Sequence


class ManagedRuntimeResource(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class ApplicationRuntimeLifecycle:
    """Start once, roll back partial startup, and stop in reverse order."""

    def __init__(self, resources: Sequence[ManagedRuntimeResource]) -> None:
        self._resources = tuple(resources)
        self._started: tuple[ManagedRuntimeResource, ...] = ()
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            started: list[ManagedRuntimeResource] = []
            try:
                for resource in self._resources:
                    resource.start()
                    started.append(resource)
            except Exception:
                for resource in reversed(started):
                    resource.stop()
                raise
            self._started = tuple(started)

    def stop(self) -> None:
        with self._lock:
            started = self._started
            self._started = ()
        for resource in reversed(started):
            resource.stop()


__all__ = ("ApplicationRuntimeLifecycle", "ManagedRuntimeResource")
