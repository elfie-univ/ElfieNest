from __future__ import annotations

import threading
import time

from infrastructure.models.validation.core_validation_worker import (
    CoreValidationWorker,
)


def test_worker_runs_periodic_pass_and_stops() -> None:
    calls: list[int] = []
    entered = threading.Event()

    def run_pass() -> None:
        calls.append(1)
        entered.set()

    worker = CoreValidationWorker(run_pass, interval_seconds=0.01)

    worker.start()
    assert entered.wait(timeout=1.0)
    time.sleep(0.03)
    worker.stop(timeout_seconds=1.0)

    assert len(calls) >= 2
    assert worker.is_running is False

def test_worker_start_is_idempotent() -> None:
    calls: list[int] = []
    entered = threading.Event()

    def run_pass() -> None:
        calls.append(1)
        entered.set()

    worker = CoreValidationWorker(run_pass, interval_seconds=0.01)

    worker.start()
    worker.start()
    assert entered.wait(timeout=1.0)
    worker.stop(timeout_seconds=1.0)

    assert worker.is_running is False
