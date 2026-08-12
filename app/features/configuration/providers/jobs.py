"""Short-lived tasks owned by local Provider administration."""

from __future__ import annotations

from dataclasses import replace
from threading import Lock
from typing import Callable

from .models import LocalProviderTaskKey, LocalProviderTaskResult
from .ports import BackgroundTaskScheduler


class LocalProviderJobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._task: LocalProviderTaskResult | None = None

    def current(self) -> LocalProviderTaskResult | None:
        with self._lock:
            return self._task

    def clear_terminal(self) -> None:
        with self._lock:
            if self._task is not None and self._task.state != "running":
                self._task = None

    def enqueue(
        self,
        key: LocalProviderTaskKey,
        scheduler: BackgroundTaskScheduler,
        worker: Callable[[], None],
    ) -> LocalProviderTaskResult:
        with self._lock:
            if self._task is not None and self._task.state == "running":
                raise RuntimeError("当前 Ollama 已有进行中的任务")
            task = LocalProviderTaskResult(key, "running", 1, None)
            self._task = task
        scheduler.add_task(lambda: self._run(task, worker))
        return task

    def _run(
        self,
        task: LocalProviderTaskResult,
        worker: Callable[[], None],
    ) -> None:
        try:
            worker()
        except Exception as error:
            message = str(error).strip() or "Ollama 任务失败"
            with self._lock:
                self._task = replace(
                    task,
                    state="failed",
                    error=message[:240],
                )
            return
        with self._lock:
            self._task = replace(task, state="completed", progress=100)


__all__ = ("LocalProviderJobManager",)
