from __future__ import annotations

from threading import Event

from infrastructure.platform.setup_runner import ThreadSetupInstallationRunner


def test_runner_cancel_sets_the_worker_cancellation_signal() -> None:
    runner = ThreadSetupInstallationRunner()
    started = Event()
    stopped = Event()

    def worker(cancelled) -> None:  # type: ignore[no-untyped-def]
        started.set()
        assert cancelled() is False
        while not cancelled():
            stopped.wait(0.01)
        stopped.set()

    assert runner.start(
        "setup",
        worker,
        timeout_seconds=10,
        on_timeout=lambda: None,
    )
    assert started.wait(1)
    assert runner.cancel("setup") is True
    assert stopped.wait(1)
    assert runner.join("setup", 1)


def test_runner_timeout_marks_the_signal_before_calling_timeout_handler() -> None:
    runner = ThreadSetupInstallationRunner()
    timed_out = Event()
    worker_stopped = Event()

    def worker(cancelled) -> None:  # type: ignore[no-untyped-def]
        while not cancelled():
            worker_stopped.wait(0.01)
        worker_stopped.set()

    def on_timeout() -> None:
        timed_out.set()

    assert runner.start(
        "setup",
        worker,
        timeout_seconds=0.02,
        on_timeout=on_timeout,
    )
    assert timed_out.wait(1)
    assert worker_stopped.wait(1)
    assert runner.join("setup", 1)
