from __future__ import annotations

from pathlib import Path

import pytest

from ai_runtime.usage.observer import (
    FallbackObservation,
    RuntimeEventStatus,
    RuntimeObserver,
    ToolCallObservation,
)
from infrastructure.models.runtime_observer import RuntimeObserverProjectionAdapter


def test_adapter_projects_without_mutating_the_runtime_observer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    observer = RuntimeObserver()
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="web_search",
            status=RuntimeEventStatus.OK,
            metadata={"query": "ElfieNest"},
        )
    )
    observer.record_fallback(
        FallbackObservation(
            from_model_key="remote_deep",
            from_provider="openai",
            to_model_key="local_fast",
            to_provider="ollama",
            reason="remote unavailable",
        )
    )

    snapshot = RuntimeObserverProjectionAdapter(observer).snapshot()

    assert snapshot.event_count == 2
    assert snapshot.last_event is not None
    assert snapshot.last_event.event_type == "fallback"
    assert snapshot.last_event.subject == "local_fast"
    assert {item.key: item.value for item in snapshot.last_event.metadata}[
        "reason"
    ] == ("remote unavailable")
    assert len(observer.snapshot()) == 2
