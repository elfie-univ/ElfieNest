from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.models.llm_api import API_DISPATCH, call_llm_api
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.models.runtime_observations import (
    FallbackObservation,
    ModelCallObservation,
    PermissionDecisionObservation,
    ProviderVerifyObservation,
    RuntimeEventStatus,
    RuntimeEventType,
    RuntimeObserver,
    ToolCallObservation,
    get_runtime_observer,
)
from infrastructure.tools.executor import ToolExecutionContext, ToolExecutor


@pytest.fixture(autouse=True)
def isolated_runtime_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))


class FakeSearchPlugin:
    def search(self, query: str) -> str:
        return f"Search result for {query}"


class FakeSandboxPlugin:
    def execute(self, code: str) -> dict[str, str | int]:
        return {"stdout": "4", "stderr": "", "exit_code": 0}


class FakeSkillsPlugin:
    def write_skill(
        self, filename: str, code: str, owner_token: str | None = None
    ) -> str:
        return "written"

    def run_skill(self, filename: str, args: str = "") -> dict[str, str | int]:
        return {"stdout": "ok", "stderr": "", "exit_code": 0}

    def list_skills(self) -> str:
        return "skills"


class FakePermissionManager:
    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None:
        return None


def test_runtime_observer_records_model_and_tool_events():
    observer = RuntimeObserver()

    observer.record_model_call(
        ModelCallObservation(
            provider="deepseek",
            model_name="deepseek-chat",
            status=RuntimeEventStatus.OK,
            prompt_chars=12,
            response_chars=8,
        )
    )
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="web_search",
            status=RuntimeEventStatus.OK,
            metadata={"query": "ElfieNest"},
        )
    )

    events = observer.snapshot()

    assert len(events) == 2
    assert events[0].event_type == RuntimeEventType.MODEL_CALL
    assert events[0].subject == "deepseek-chat"
    assert events[0].metadata["provider"] == "deepseek"
    assert events[1].event_type == RuntimeEventType.TOOL_CALL
    assert events[1].subject == "web_search"


def test_runtime_observer_records_permission_fallback_and_provider_events():
    observer = RuntimeObserver()

    observer.record_permission_decision(
        PermissionDecisionObservation(
            action="RUN_SKILL",
            resource="code_sandbox",
            allowed=False,
            mode="deny",
            reason="policy denied",
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
    observer.record_provider_verify(
        ProviderVerifyObservation(
            provider_id="ollama",
            status=RuntimeEventStatus.OK,
            provider_status="active",
            latency_ms=12.5,
        )
    )

    events = observer.snapshot()

    assert events[0].event_type == RuntimeEventType.PERMISSION_DECISION
    assert events[0].status == RuntimeEventStatus.ERROR
    assert events[0].subject == "RUN_SKILL"
    assert events[0].metadata["resource"] == "code_sandbox"
    assert events[0].metadata["allowed"] is False
    assert events[1].event_type == RuntimeEventType.FALLBACK
    assert events[1].subject == "local_fast"
    assert events[1].metadata["from_model_key"] == "remote_deep"
    assert events[2].event_type == RuntimeEventType.PROVIDER_VERIFY
    assert events[2].subject == "ollama"
    assert events[2].metadata["latency_ms"] == 12.5


def test_runtime_observer_flush_resets_without_creating_legacy_jsonl(tmp_path: Path):
    observer = RuntimeObserver()
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="code_sandbox",
            status=RuntimeEventStatus.ERROR,
            metadata={"exit_code": 1},
        )
    )

    observer.flush("tick_001")

    assert observer.snapshot() == ()
    assert not (tmp_path / "runtime_events.jsonl").exists()


def test_call_llm_api_records_successful_model_call(monkeypatch: pytest.MonkeyPatch):
    observer = get_runtime_observer()
    observer.reset()

    def fake_dispatch(
        api_base: str,
        api_key: str,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        provider: str,
    ) -> tuple[str, dict[str, int]]:
        return "observed response", {"prompt_tokens": 2, "completion_tokens": 3}

    monkeypatch.setitem(API_DISPATCH, "chat_completions", fake_dispatch)
    config = LLMRuntimeConfig()
    config.providers["observed"] = {
        "api_base": "https://api.observed.test",
        "api_key": "",
        "api_mode": "chat_completions",
    }

    result = call_llm_api(
        config,
        "observed",
        "observed-model",
        [{"role": "user", "content": "hello"}],
        0.1,
        100,
    )

    events = observer.snapshot()
    observer.reset()
    assert result == "observed response"
    assert events[-1].event_type == RuntimeEventType.MODEL_CALL
    assert events[-1].status == RuntimeEventStatus.OK
    assert events[-1].subject == "observed-model"
    assert events[-1].metadata["provider"] == "observed"
    assert events[-1].metadata["response_chars"] == len("observed response")


def test_call_llm_api_records_failed_model_call(monkeypatch: pytest.MonkeyPatch):
    observer = get_runtime_observer()
    observer.reset()

    def fake_dispatch(
        api_base: str,
        api_key: str,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        provider: str,
    ) -> tuple[str, dict[str, int]]:
        raise RuntimeError("provider down")

    monkeypatch.setitem(API_DISPATCH, "chat_completions", fake_dispatch)
    config = LLMRuntimeConfig()
    config.providers["broken"] = {
        "api_base": "https://api.broken.test",
        "api_key": "",
        "api_mode": "chat_completions",
    }

    with pytest.raises(RuntimeError):
        call_llm_api(
            config,
            "broken",
            "broken-model",
            [{"role": "user", "content": "hello"}],
            0.1,
            100,
        )

    events = observer.snapshot()
    observer.reset()
    assert events[-1].event_type == RuntimeEventType.MODEL_CALL
    assert events[-1].status == RuntimeEventStatus.ERROR
    assert events[-1].subject == "broken-model"
    assert events[-1].metadata["error_type"] == "RuntimeError"


def test_tool_executor_records_tool_observation():
    observer = get_runtime_observer()
    observer.reset()
    executor = ToolExecutor(
        ToolExecutionContext(
            allowed_skills=("web_search",),
            search_plugin=FakeSearchPlugin(),
            permission_manager=FakePermissionManager(),
            observation_port=observer,
        )
    )

    result = executor.execute("[SEARCH]ElfieNest[/SEARCH]")

    events = observer.snapshot()
    observer.reset()
    assert result is not None
    assert events[-1].event_type == RuntimeEventType.TOOL_CALL
    assert events[-1].status == RuntimeEventStatus.OK
    assert events[-1].subject == "web_search"
    assert "query" not in events[-1].metadata
    assert events[-1].metadata["tool_call_index"] == 1
