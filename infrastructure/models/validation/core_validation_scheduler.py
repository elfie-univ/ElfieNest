"""Cross-process, core-only validation scheduling.

The scheduler owns no Provider facts and performs no discovery.  It receives
the current derived ServingFood index, asks a read-only availability projection
whether a subject is due, and invokes one injected validator.  A short OS file
lease makes concurrent Core processes converge on one active worker.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, cast

from infrastructure.models.validation.serving_food import ServingFoodIndex

if os.name == "nt":
    import msvcrt
else:
    import fcntl


CORE_VALIDATION_MAX_AGE = timedelta(hours=24)
_LEASE_BYTE = 0


@dataclass(frozen=True)
class CoreValidationTask:
    reference: str
    channel: str
    generation: str


@dataclass(frozen=True)
class CoreValidationRun:
    acquired: bool
    generation: str
    attempted: tuple[CoreValidationTask, ...] = ()
    cancelled: tuple[CoreValidationTask, ...] = ()
    results: Mapping[CoreValidationTask, object] | None = None


AvailabilityReader = Callable[[str, str], object]
Validator = Callable[[str, str], object]
IndexReader = Callable[[], ServingFoodIndex]


class CoreValidationScheduler:
    """Run only due core endpoint/channel checks under a process lease."""

    def __init__(
        self,
        lease_path: str | Path,
        validator: Validator,
        *,
        current_index: IndexReader | None = None,
        max_age: timedelta = CORE_VALIDATION_MAX_AGE,
    ) -> None:
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        self._lease_path = Path(lease_path)
        self._validator = validator
        self._current_index = current_index
        self._max_age = max_age
        self._pending: dict[tuple[str, str], CoreValidationTask] = {}
        self._lock = threading.Lock()

    def refresh(self, index: ServingFoodIndex) -> tuple[CoreValidationTask, ...]:
        """Replace queued work with the current index generation."""
        tasks = tuple(
            CoreValidationTask(reference, channel, index.generation)
            for reference, channels in _core_channels(index).items()
            for channel in channels
        )
        with self._lock:
            self._pending = {task_key(task): task for task in tasks}
        return tasks

    def run_due(
        self,
        index: ServingFoodIndex,
        availability: AvailabilityReader,
        *,
        now: datetime | None = None,
    ) -> CoreValidationRun:
        """Validate due current-generation tasks and cancel stale queued work."""
        current = _utc(now or datetime.now(timezone.utc))
        self.refresh(index)
        generation = index.generation
        with self._lease():
            if self._lease_unavailable:
                return CoreValidationRun(False, generation)
            attempted: list[CoreValidationTask] = []
            cancelled: list[CoreValidationTask] = []
            results: dict[CoreValidationTask, object] = {}
            for task in self._pending_tasks():
                latest = self._current_index() if self._current_index else index
                if latest.generation != task.generation:
                    cancelled.append(task)
                    self._remove(task)
                    continue
                state = availability(task.reference, task.channel)
                if not _is_due(state, current, self._max_age):
                    self._remove(task)
                    continue
                try:
                    results[task] = self._validator(task.reference, task.channel)
                except Exception as error:  # noqa: BLE001 - preserve other core tasks
                    results[task] = error
                attempted.append(task)
                self._remove(task)
            return CoreValidationRun(
                True,
                generation,
                tuple(attempted),
                tuple(cancelled),
                results,
            )

    @property
    def _lease_unavailable(self) -> bool:
        return getattr(self, "_lease_failed", False)

    @contextmanager
    def _lease(self) -> Iterator[None]:
        self._lease_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lease_path.open("a+b")
        self._lease_failed = False
        try:
            try:
                _try_lock(handle)
            except (BlockingIOError, OSError):
                self._lease_failed = True
                yield
                return
            yield
        finally:
            if not self._lease_failed:
                _unlock(handle)
            handle.close()

    def _pending_tasks(self) -> tuple[CoreValidationTask, ...]:
        with self._lock:
            return tuple(self._pending.values())

    def _remove(self, task: CoreValidationTask) -> None:
        with self._lock:
            self._pending.pop(task_key(task), None)


def _core_channels(index: ServingFoodIndex) -> dict[str, tuple[str, ...]]:
    channels: dict[str, set[str]] = {}
    for endpoint in index.core_endpoints:
        endpoint_channels = channels.setdefault(endpoint.reference, set())
        # Every core endpoint gets one ordinary text/reachability check.  The
        # role-specific channels are separate proof obligations.
        endpoint_channels.add("text")
        for role in endpoint.roles:
            if role in {"reasoning", "vision", "tool"}:
                endpoint_channels.add(role)
    return {reference: tuple(sorted(values)) for reference, values in channels.items()}


def _is_due(state: object, now: datetime, max_age: timedelta) -> bool:
    expires_at = getattr(state, "expires_at", None)
    if isinstance(expires_at, str):
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expiry = None
        if expiry is not None and expiry.tzinfo is not None:
            if now < expiry.astimezone(timezone.utc):
                return False
    status = getattr(state, "status", "unknown")
    if status in {"unknown", "unavailable", "degraded"}:
        return True
    observed = getattr(state, "observed_at", None)
    if not isinstance(observed, str):
        return True
    try:
        timestamp = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return True
    if timestamp.tzinfo is None:
        return True
    return now - timestamp.astimezone(timezone.utc) >= max_age


def task_key(task: CoreValidationTask) -> tuple[str, str]:
    return (task.reference, task.channel)


def _try_lock(handle) -> None:
    handle.seek(_LEASE_BYTE)
    if os.name == "nt":
        msvcrt_module = cast(Any, msvcrt)
        msvcrt_module.locking(handle.fileno(), msvcrt_module.LK_NBLCK, 1)
    else:
        fcntl_module = cast(Any, fcntl)
        fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX | fcntl_module.LOCK_NB)


def _unlock(handle) -> None:
    try:
        if os.name == "nt":
            handle.seek(_LEASE_BYTE)
            msvcrt_module = cast(Any, msvcrt)
            msvcrt_module.locking(handle.fileno(), msvcrt_module.LK_UNLCK, 1)
        else:
            fcntl_module = cast(Any, fcntl)
            fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)
    except OSError:
        pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = (
    "CORE_VALIDATION_MAX_AGE",
    "CoreValidationRun",
    "CoreValidationScheduler",
    "CoreValidationTask",
    "task_key",
)
