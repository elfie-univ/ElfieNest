"""Explicit isolated cortical worker for one Elfie."""

from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Lock, Thread
from typing import Deque, Dict, NamedTuple, Optional, Protocol

from elfie.brain.decision_decoder import (
    DecisionDecodeResult,
    DecisionDecodeSeed,
    DecisionPlanDecoder,
)
from elfie.brain.runtime_port import ModelGenerationRequest, ModelPort


@dataclass(frozen=True)
class WorkerNotRunningError(RuntimeError):
    """Raised when work is submitted outside the explicit lifecycle."""

    reason: str = "cortical worker is not running"

    def __str__(self) -> str:
        return self.reason


class WorkerCapacityError(RuntimeError):
    """Raised when isolated hung calls have exhausted the worker capacity."""

    __slots__ = ("active_calls", "capacity")

    def __init__(self, *, active_calls: int, capacity: int) -> None:
        self.active_calls = active_calls
        self.capacity = capacity
        super().__init__(active_calls, capacity)

    def __str__(self) -> str:
        return (
            "cortical worker capacity exhausted: "
            f"{self.active_calls}/{self.capacity} provider calls are still active"
        )


class WorkerQueueFullError(RuntimeError):
    """Raised when queued cortical work reaches the configured bound."""

    __slots__ = ("queued_tasks", "capacity")

    def __init__(self, *, queued_tasks: int, capacity: int) -> None:
        self.queued_tasks = queued_tasks
        self.capacity = capacity
        super().__init__(queued_tasks, capacity)

    def __str__(self) -> str:
        return (
            "cortical worker queue full: "
            f"{self.queued_tasks}/{self.capacity} tasks are waiting"
        )


class CorticalTaskView(Protocol):
    """Typed input required for one generation and decode operation."""

    @property
    def request(self) -> ModelGenerationRequest:
        """Return the immutable model request."""

    @property
    def seed(self) -> DecisionDecodeSeed:
        """Return the immutable decode seed."""


@dataclass(frozen=True)
class CorticalTask:
    """Concrete immutable cortical task."""

    request: ModelGenerationRequest
    seed: DecisionDecodeSeed


@dataclass(frozen=True)
class CorticalTurnResult:
    """Validated worker result returned to BrainCoordinator."""

    decode: DecisionDecodeResult


class CorticalExecutionPort(Protocol):
    """Non-blocking execution capability consumed by BrainCoordinator."""

    def start(self) -> None:
        """Start the explicit worker lifecycle."""

    def submit(self, task: CorticalTaskView) -> Future[CorticalTurnResult]:
        """Queue one task on the per-Elfie cortical worker."""

    def abandon(self, future: Future[CorticalTurnResult]) -> None:
        """Detach a timed-out call so a replacement may start."""

    def stop(self) -> None:
        """Stop accepting new work."""

    def join(self) -> None:
        """Wait for worker resources to terminate."""


class _QueuedTask(NamedTuple):
    task: CorticalTaskView
    future: Future[CorticalTurnResult]


class _ActiveCall(NamedTuple):
    task: CorticalTaskView
    thread: Thread


class CorticalWorker:
    """Serialize healthy calls while isolating one abandoned provider call."""

    def __init__(
        self,
        *,
        model_port: ModelPort,
        decoder: DecisionPlanDecoder,
        max_active_calls: int = 2,
        max_queued_tasks: int = 16,
    ) -> None:
        self._model_port = model_port
        self._decoder = decoder
        self._max_active_calls = max_active_calls
        self._max_queued_tasks = max_queued_tasks
        self._queued: Deque[_QueuedTask] = deque()
        self._current: Optional[Future[CorticalTurnResult]] = None
        self._active: Dict[Future[CorticalTurnResult], _ActiveCall] = {}
        self._accepting = False
        self._thread_sequence = 0
        self._lock = Lock()

    def start(self) -> None:
        """Start once; repeated calls while running are idempotent."""
        with self._lock:
            if self._accepting:
                return
            self._accepting = True

    def submit(self, task: CorticalTaskView) -> Future[CorticalTurnResult]:
        """Submit without blocking the caller."""
        thread: Optional[Thread] = None
        future: Future[CorticalTurnResult] = Future()
        with self._lock:
            if not self._accepting:
                raise WorkerNotRunningError()
            if self._current is None:
                if len(self._active) >= self._max_active_calls:
                    raise WorkerCapacityError(
                        active_calls=len(self._active),
                        capacity=self._max_active_calls,
                    )
                thread = self._prepare_thread_locked(_QueuedTask(task, future))
            else:
                if len(self._queued) >= self._max_queued_tasks:
                    raise WorkerQueueFullError(
                        queued_tasks=len(self._queued),
                        capacity=self._max_queued_tasks,
                    )
                self._queued.append(_QueuedTask(task, future))
        if thread is not None:
            thread.start()
        return future

    def abandon(self, future: Future[CorticalTurnResult]) -> None:
        """Detach running work; its daemon thread may finish and report late."""
        thread: Optional[Thread] = None
        request: Optional[ModelGenerationRequest] = None
        with self._lock:
            if future is self._current:
                self._current = None
                future.cancel()
                active = self._active.get(future)
                if active is not None:
                    request = active.task.request
                thread = self._prepare_next_locked()
            else:
                self._cancel_queued_locked(future)
        if request is not None:
            self._model_port.abandon(request)
        if thread is not None:
            thread.start()

    def stop(self) -> None:
        """Stop accepting new tasks and cancel queued work."""
        request: Optional[ModelGenerationRequest] = None
        with self._lock:
            self._accepting = False
            while self._queued:
                self._queued.popleft().future.cancel()
            current = self._current
            self._current = None
            if current is not None:
                current.cancel()
                active = self._active.get(current)
                if active is not None:
                    request = active.task.request
        if request is not None:
            self._model_port.abandon(request)

    def join(self) -> None:
        """Return after logical shutdown without waiting for isolated calls."""

    def _prepare_thread_locked(self, queued: _QueuedTask) -> Thread:
        self._thread_sequence += 1
        thread = Thread(
            target=self._execute,
            args=(queued,),
            name=f"elfie-cortical-{self._thread_sequence}",
            daemon=True,
        )
        self._current = queued.future
        self._active[queued.future] = _ActiveCall(queued.task, thread)
        return thread

    def _prepare_next_locked(self) -> Optional[Thread]:
        if not self._accepting or self._current is not None:
            return None
        while self._queued:
            queued = self._queued.popleft()
            if queued.future.cancelled():
                continue
            if len(self._active) >= self._max_active_calls:
                self._queued.appendleft(queued)
                return None
            return self._prepare_thread_locked(queued)
        return None

    def _cancel_queued_locked(self, future: Future[CorticalTurnResult]) -> None:
        for queued in tuple(self._queued):
            if queued.future is future:
                self._queued.remove(queued)
                future.cancel()
                return

    def _execute(self, queued: _QueuedTask) -> None:
        future = queued.future
        if not future.set_running_or_notify_cancel():
            self._finish(future)
            return
        try:
            result = self._run(queued.task)
        except Exception as error:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - Future boundary
            future.set_exception(error)
        else:
            future.set_result(result)
        finally:
            self._finish(future)

    def _finish(self, future: Future[CorticalTurnResult]) -> None:
        thread: Optional[Thread] = None
        with self._lock:
            self._active.pop(future, None)
            if future is self._current:
                self._current = None
            thread = self._prepare_next_locked()
        if thread is not None:
            thread.start()

    def _run(self, task: CorticalTaskView) -> CorticalTurnResult:
        capabilities = self._model_port.capabilities()
        generation = self._model_port.generate(task.request)

        def repair(raw_text: str, errors: tuple[str, ...]) -> str:
            repair_prompt = (
                "Repair the following invalid DecisionPlan JSON. Return JSON only.\n"
                f"Errors: {'; '.join(errors)}\nRaw output:\n{raw_text}"
            )
            request = task.request.model_copy(update={"user_prompt": repair_prompt})
            return self._model_port.generate(request).text

        decode = self._decoder.decode(
            seed=task.seed,
            generation=generation,
            capabilities=capabilities,
            repair_callback=None if capabilities.plain_text_only else repair,
        )
        return CorticalTurnResult(decode=decode)


__all__ = (
    "CorticalExecutionPort",
    "CorticalTask",
    "CorticalTaskView",
    "CorticalTurnResult",
    "CorticalWorker",
    "WorkerCapacityError",
    "WorkerQueueFullError",
    "WorkerNotRunningError",
)
