from __future__ import annotations

import pytest

from app.orchestration.lifecycle.runtime_resources import ApplicationRuntimeLifecycle


class Resource:
    def __init__(self, name: str, events: list[str], *, fail: bool = False) -> None:
        self.name = name
        self.events = events
        self.fail = fail

    def start(self) -> None:
        self.events.append(f"start:{self.name}")
        if self.fail:
            raise RuntimeError(self.name)

    def stop(self) -> None:
        self.events.append(f"stop:{self.name}")


def test_lifecycle_owns_start_rollback_and_reverse_stop() -> None:
    events: list[str] = []
    lifecycle = ApplicationRuntimeLifecycle(
        (Resource("one", events), Resource("two", events, fail=True))
    )

    with pytest.raises(RuntimeError):
        lifecycle.start()

    assert events == ["start:one", "start:two", "stop:one"]
