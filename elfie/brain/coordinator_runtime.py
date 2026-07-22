"""Thread-safe runtime primitives used by BrainCoordinator."""

from __future__ import annotations

from queue import Queue
from threading import Condition, Lock, Thread
from typing import Callable, Optional, Tuple

from elfie.brain.coordinator_types import ControlMessage, StopControl
from elfie.brain.cortical_worker import CorticalExecutionPort
from elfie.brain.turn_outcome import TurnOutcome
from elfie.message_types import ElfieId


class InvalidOutcomeCountError(ValueError):
    """An observer requested a negative cognitive outcome count."""


class CoordinatorRuntime:
    """Own the coordinator thread, mailbox, and cortical worker lifecycle."""

    def __init__(
        self,
        elfie_id: ElfieId,
        cortical_worker: CorticalExecutionPort,
    ) -> None:
        self._elfie_id = elfie_id
        self._worker = cortical_worker
        self._mailbox: Queue[ControlMessage] = Queue()
        self._thread: Optional[Thread] = None
        self._lock = Lock()
        self._stop_requested = False

    def start(self, owner_loop: Callable[[], None]) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._mailbox = Queue()
            self._stop_requested = False
            self._worker.start()
            self._thread = Thread(
                target=owner_loop,
                name=f"elfie-brain-{self._elfie_id}",
                daemon=False,
            )
            self._thread.start()

    def post(self, message: ControlMessage) -> None:
        self._mailbox.put(message)

    def receive(self) -> ControlMessage:
        return self._mailbox.get()

    def stop(self) -> None:
        with self._lock:
            if self._stop_requested or self._thread is None:
                return
            self._stop_requested = True
            self._mailbox.put(StopControl())
        self._worker.stop()

    def join(self) -> None:
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join()
        self._worker.join()

    @property
    def is_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()


class TurnOutcomeBuffer:
    """Publish immutable turn outcomes to observers without polling."""

    def __init__(self) -> None:
        self._items: list[TurnOutcome] = []
        self._changed = Condition()

    def snapshot(self) -> Tuple[TurnOutcome, ...]:
        with self._changed:
            return tuple(self._items)

    def wait(self, timeout: float) -> None:
        self.wait_for_count(1, timeout)

    def wait_for_count(self, count: int, timeout: float) -> None:
        """Wait until at least ``count`` immutable outcomes are available."""
        if count < 0:
            raise InvalidOutcomeCountError("outcome count cannot be negative")
        with self._changed:
            reached = self._changed.wait_for(
                lambda: len(self._items) >= count,
                timeout=timeout,
            )
        if not reached:
            raise TimeoutError("brain coordinator outcome timed out")

    def record(self, outcome: TurnOutcome) -> None:
        with self._changed:
            self._items.append(outcome)
            self._changed.notify_all()


__all__ = ("CoordinatorRuntime", "TurnOutcomeBuffer")
