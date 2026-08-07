"""Single-owner Setup installation worker and its process-local thread manager."""

from __future__ import annotations

import logging
from threading import Lock, Thread
from typing import Callable

from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRecord,
    SetupInstallRepository,
)

logger = logging.getLogger("app.features.setup.installer")

SetupInstallWorker = Callable[[], None]


class SetupInstallJobManager:
    """Allow one resumable installation thread per database."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._threads: dict[str, Thread] = {}

    def start(self, *, db_path: str, worker: SetupInstallWorker) -> SetupInstallRecord:
        repository = SetupInstallRepository(db_path)
        existing = repository.get()
        with self._lock:
            current = self._threads.get(db_path)
            if current is not None:
                if current.is_alive() or existing.task_status == "running":
                    return existing
        record = repository.begin_or_resume()
        if record.status == "completed":
            return record
        with self._lock:
            current = self._threads.get(db_path)
            if current is not None and current.is_alive():
                return record
            thread = Thread(
                target=self._run,
                args=(db_path, worker),
                name="elfienest-setup-install",
                daemon=True,
            )
            self._threads[db_path] = thread
        thread.start()
        return record

    def join(self, db_path: str, timeout: float) -> bool:
        with self._lock:
            thread = self._threads.get(db_path)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    @staticmethod
    def _run(db_path: str, worker: SetupInstallWorker) -> None:
        try:
            worker()
        except Exception as error:  # noqa: BLE001 - task boundary must persist all failures
            logger.exception("Setup installation worker failed")
            repository = SetupInstallRepository(db_path)
            record = repository.get()
            action_key = record.install_action or "unknown"
            repository.fail(action_key, _safe_error(str(error)))


def recover_interrupted_setup_install(db_path: str) -> None:
    """Turn an orphaned running task into a retryable failed task on startup."""
    SetupInstallRepository(db_path).recover_running("应用重启前的 Setup 安装任务未完成")


def build_setup_install_worker(db_path: str) -> SetupInstallWorker:
    """Build the product worker; phase actions are supplied by the Setup domain."""
    def unavailable() -> None:
        from app.features.setup.install_actions import run_setup_installation

        run_setup_installation(db_path)

    return unavailable


def _safe_error(message: str) -> str:
    lowered = message.lower()
    if any(marker in lowered for marker in ("password", "token", "secret", "api key")):
        return "安装失败；敏感错误详情已隐藏。"
    return message.strip()[:512] or "Setup 安装失败"


__all__ = (
    "SetupInstallJobManager",
    "SetupInstallWorker",
    "build_setup_install_worker",
    "recover_interrupted_setup_install",
)
