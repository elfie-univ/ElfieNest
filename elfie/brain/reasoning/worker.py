"""Explicit isolated reasoning worker for one Elfie."""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Deque, Dict, NamedTuple, Optional, Protocol

from elfie.brain.activity.preflight import ActivityPreflightPort
from elfie.brain.energy.contracts import CognitiveBudgetReservation
from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeResult,
    DecisionDecodeSeed,
    DecisionPlanDecoder,
)
from elfie.brain.reasoning.model_port import ModelGenerationRequest, ModelPort
from elfie.brain.reasoning.reply_safety import ReplySafetyContext
from elfie.brain.reasoning.run import (
    ReasoningBudget,
    ReasoningRun,
    ReasoningRunResult,
)
from elfie.brain.reasoning.settlement import TurnStateCandidate
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.message_types import ElfieId


@dataclass(frozen=True)
class WorkerNotRunningError(RuntimeError):
    """Raised when work is submitted outside the explicit lifecycle."""

    reason: str = "reasoning worker is not running"

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
            "reasoning worker capacity exhausted: "
            f"{self.active_calls}/{self.capacity} provider calls are still active"
        )


class WorkerQueueFullError(RuntimeError):
    """Raised when queued reasoning work reaches the configured bound."""

    __slots__ = ("queued_tasks", "capacity")

    def __init__(self, *, queued_tasks: int, capacity: int) -> None:
        self.queued_tasks = queued_tasks
        self.capacity = capacity
        super().__init__(queued_tasks, capacity)

    def __str__(self) -> str:
        return (
            "reasoning worker queue full: "
            f"{self.queued_tasks}/{self.capacity} tasks are waiting"
        )


class ReasoningTaskView(Protocol):
    """Typed input required for one generation and decode operation."""

    @property
    def request(self) -> ModelGenerationRequest:
        """Return the immutable model request."""

    @property
    def seed(self) -> DecisionDecodeSeed:
        """Return the immutable decode seed."""

    @property
    def tool_scope_id(self) -> ElfieId | None:
        """Return the owning Elfie scope for local semantic tools."""

    @property
    def reasoning_budget(self) -> ReasoningBudget | None:
        """Return the per-Turn budget selected by Energy, if any."""

    @property
    def state_candidates(self) -> tuple[TurnStateCandidate, ...]:
        """Return explicit owner candidates prepared before model execution."""

    @property
    def reply_safety_context(self) -> ReplySafetyContext | None:
        """Return current-state evidence used by direct reply validation."""


@dataclass(frozen=True)
class ReasoningTask:
    """Concrete immutable reasoning task."""

    request: ModelGenerationRequest
    seed: DecisionDecodeSeed
    tool_scope_id: ElfieId | None = None
    reasoning_budget: ReasoningBudget | None = None
    energy_reservation: CognitiveBudgetReservation | None = None
    state_candidates: tuple[TurnStateCandidate, ...] = ()
    reply_safety_context: ReplySafetyContext | None = None


@dataclass(frozen=True)
class ReasoningTurnResult:
    """Validated worker result returned to BrainCoordinator."""

    decode: DecisionDecodeResult
    reasoning: ReasoningRunResult


class ReasoningExecutionPort(Protocol):
    """Non-blocking execution capability consumed by BrainCoordinator."""

    def start(self) -> None:
        """Start the explicit worker lifecycle."""

    def submit(self, task: ReasoningTaskView) -> Future[ReasoningTurnResult]:
        """Queue one task on the per-Elfie reasoning worker."""

    def abandon(self, future: Future[ReasoningTurnResult]) -> None:
        """Detach a timed-out call so a replacement may start."""

    def stop(self) -> None:
        """Stop accepting new work."""

    def join(self) -> None:
        """Wait for worker resources to terminate."""


class _QueuedTask(NamedTuple):
    task: ReasoningTaskView
    future: Future[ReasoningTurnResult]
    cancellation: Event


class _ActiveCall(NamedTuple):
    task: ReasoningTaskView
    thread: Thread
    cancellation: Event


class ReasoningWorker:
    """Serialize healthy calls while isolating one abandoned provider call."""

    def __init__(
        self,
        *,
        model_port: ModelPort,
        decoder: DecisionPlanDecoder,
        tool_port: ToolPort | None = None,
        activity_preflight: ActivityPreflightPort | None = None,
        reasoning_budget: ReasoningBudget | None = None,
        max_active_calls: int = 2,
        max_queued_tasks: int = 16,
    ) -> None:
        self._model_port = model_port
        self._decoder = decoder
        self._tool_port = tool_port
        self._activity_preflight = activity_preflight
        self._reasoning_budget = reasoning_budget
        self._max_active_calls = max_active_calls
        self._max_queued_tasks = max_queued_tasks
        self._queued: Deque[_QueuedTask] = deque()
        self._current: Optional[Future[ReasoningTurnResult]] = None
        self._active: Dict[Future[ReasoningTurnResult], _ActiveCall] = {}
        self._accepting = False
        self._thread_sequence = 0
        self._lock = Lock()

    def start(self) -> None:
        """Start once; repeated calls while running are idempotent."""
        with self._lock:
            if self._accepting:
                return
            self._accepting = True

    def submit(self, task: ReasoningTaskView) -> Future[ReasoningTurnResult]:
        """Submit without blocking the caller."""
        thread: Optional[Thread] = None
        future: Future[ReasoningTurnResult] = Future()
        cancellation = Event()
        with self._lock:
            if not self._accepting:
                raise WorkerNotRunningError()
            if self._current is None:
                if len(self._active) >= self._max_active_calls:
                    raise WorkerCapacityError(
                        active_calls=len(self._active),
                        capacity=self._max_active_calls,
                    )
                thread = self._prepare_thread_locked(
                    _QueuedTask(task, future, cancellation)
                )
            else:
                if len(self._queued) >= self._max_queued_tasks:
                    raise WorkerQueueFullError(
                        queued_tasks=len(self._queued),
                        capacity=self._max_queued_tasks,
                    )
                self._queued.append(_QueuedTask(task, future, cancellation))
        if thread is not None:
            thread.start()
        return future

    def abandon(self, future: Future[ReasoningTurnResult]) -> None:
        """Detach running work; its daemon thread may finish and report late."""
        thread: Optional[Thread] = None
        request: Optional[ModelGenerationRequest] = None
        with self._lock:
            if future is self._current:
                self._current = None
                future.cancel()
                active = self._active.get(future)
                if active is not None:
                    active.cancellation.set()
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
                    active.cancellation.set()
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
            name=f"elfie-reasoning-{self._thread_sequence}",
            daemon=True,
        )
        self._current = queued.future
        self._active[queued.future] = _ActiveCall(
            queued.task,
            thread,
            queued.cancellation,
        )
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

    def _cancel_queued_locked(self, future: Future[ReasoningTurnResult]) -> None:
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
            result = self._run(queued.task, queued.cancellation)
        except Exception as error:  # noqa: BLE001 - Future boundary owns failure mapping
            future.set_exception(error)
        else:
            future.set_result(result)
        finally:
            self._finish(future)

    def _finish(self, future: Future[ReasoningTurnResult]) -> None:
        thread: Optional[Thread] = None
        with self._lock:
            self._active.pop(future, None)
            if future is self._current:
                self._current = None
            thread = self._prepare_next_locked()
        if thread is not None:
            thread.start()

    def _run(
        self,
        task: ReasoningTaskView,
        cancellation: Event,
    ) -> ReasoningTurnResult:
        reasoning = ReasoningRun(
            model_port=self._model_port,
            decoder=self._decoder,
            tool_port=self._tool_port,
            activity_preflight=self._activity_preflight,
            budget=getattr(task, "reasoning_budget", None) or self._reasoning_budget,
        ).run(task, cancellation=cancellation)
        return ReasoningTurnResult(
            decode=reasoning.decode,
            reasoning=reasoning,
        )


__all__ = (
    "ReasoningExecutionPort",
    "ReasoningTask",
    "ReasoningTaskView",
    "ReasoningTurnResult",
    "ReasoningWorker",
    "WorkerCapacityError",
    "WorkerQueueFullError",
    "WorkerNotRunningError",
)
