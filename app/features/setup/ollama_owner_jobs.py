"""Short-lived background tasks used by the management Ollama card."""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from typing import Callable, Literal, Protocol

OllamaTaskKey = Literal["install", "model_pull"]
OllamaTaskState = Literal["running", "completed", "failed"]


@dataclass(frozen=True)
class OllamaTask:
    key: OllamaTaskKey
    state: OllamaTaskState
    progress: int
    error: str | None


class BackgroundTaskScheduler(Protocol):
    """The small part of FastAPI BackgroundTasks needed by this feature."""

    def add_task(
        self,
        func: Callable[..., None],
        *args: str | OllamaTask | Callable[[], None],
    ) -> None: ...


class OllamaOwnerJobManager:
    """Keep one short-lived Owner task per data root while it runs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, OllamaTask] = {}

    def current(self, scope: str) -> OllamaTask | None:
        with self._lock:
            return self._tasks.get(scope)

    def clear(self, scope: str) -> None:
        """Forget a terminal task after its owning action has recovered."""
        with self._lock:
            current = self._tasks.get(scope)
            if current is not None and current.state != "running":
                self._tasks.pop(scope, None)

    def enqueue(
        self,
        scope: str,
        key: OllamaTaskKey,
        background_tasks: BackgroundTaskScheduler,
        worker: Callable[[], None],
    ) -> OllamaTask:
        with self._lock:
            current = self._tasks.get(scope)
            if current is not None and current.state == "running":
                raise RuntimeError("当前 Ollama 已有进行中的任务")
            task = OllamaTask(key=key, state="running", progress=1, error=None)
            self._tasks[scope] = task
        background_tasks.add_task(self._run, scope, task, worker)
        return task

    def _run(
        self,
        scope: str,
        task: OllamaTask,
        worker: Callable[[], None],
    ) -> None:
        try:
            worker()
        except Exception as exc:
            with self._lock:
                self._tasks[scope] = replace(
                    task,
                    state="failed",
                    error=_task_error(exc),
                )
            return
        with self._lock:
            self._tasks[scope] = replace(task, state="completed", progress=100)


def _task_error(error: Exception) -> str:
    message = str(error).strip() or "Ollama 任务失败"
    return message[:240]
