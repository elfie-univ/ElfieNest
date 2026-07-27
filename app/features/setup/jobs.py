"""In-process workers for explicitly approved, resumable Setup tasks."""

from __future__ import annotations

from threading import Lock, Thread
from typing import Callable, Dict, Optional

from app.features.setup.progress import (
    SetupTask,
    begin_setup_task,
    record_setup_task_failure,
)

OllamaInstallWorker = Callable[[], None]


class OllamaInstallJobManager:
    """Owns one worker per setup database; SQLite remains the status authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._threads: Dict[str, Thread] = {}

    def start(self, *, db_path: str, worker: OllamaInstallWorker) -> SetupTask:
        """Start an approved Ollama installer without holding the HTTP request."""
        return self._start(db_path, step=2, task_key="ollama_install", worker=worker)

    def start_model_pull(
        self, *, db_path: str, worker: OllamaInstallWorker
    ) -> SetupTask:
        """Start one confirmed model pull without holding the HTTP request."""
        return self._start(db_path, step=4, task_key="model_pull", worker=worker)

    def _start(
        self,
        db_path: str,
        *,
        step: int,
        task_key: str,
        worker: OllamaInstallWorker,
    ) -> SetupTask:
        task = begin_setup_task(db_path, step=step, task_key=task_key)
        thread = Thread(
            target=self._run,
            args=(db_path, step, task_key, worker),
            name=f"elfienest-{task_key}",
            daemon=True,
        )
        with self._lock:
            if db_path in self._threads and self._threads[db_path].is_alive():
                raise RuntimeError("当前 Setup 已有 Ollama 安装任务")
            self._threads[db_path] = thread
        thread.start()
        return task

    def join(self, db_path: str, timeout: float) -> bool:
        """Join a task in deterministic tests; product callers never need this."""
        with self._lock:
            thread: Optional[Thread] = self._threads.get(db_path)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _run(
        self,
        db_path: str,
        step: int,
        task_key: str,
        worker: OllamaInstallWorker,
    ) -> None:
        try:
            worker()
        except RuntimeError as exc:
            record_setup_task_failure(
                db_path,
                step=step,
                task_key=task_key,
                error_message=str(exc),
            )
