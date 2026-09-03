from __future__ import annotations

from pathlib import Path

import pytest

from elfie.brain.reasoning.tool_port import ToolRequest
from infrastructure.models.inference.llm_api import (
    API_DISPATCH,
    call_llm_api,
    call_llm_api_result,
)
from infrastructure.models.model_execution_observations import (
    FallbackObservation,
    ModelCallObservation,
    ModelExecutionEventStatus,
    ModelExecutionEventType,
    ModelExecutionObserver,
    PermissionDecisionObservation,
    ProviderVerifyObservation,
    ToolCallObservation,
    get_model_execution_observer,
)
from infrastructure.tools.execution.executor import ToolExecutionContext, ToolExecutor
from test.support.model_execution import model_execution_config


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


def test_model_execution_observer_records_model_and_tool_events():
    observer = ModelExecutionObserver()

    observer.record_model_call(
        ModelCallObservation(
            provider="deepseek",
            model_name="deepseek-chat",
            status=ModelExecutionEventStatus.OK,
            prompt_chars=12,
            response_chars=8,
        )
    )
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="web_search",
            status=ModelExecutionEventStatus.OK,
            metadata={"query": "ElfieNest"},
        )
    )

    events = observer.snapshot()

    assert len(events) == 2
    assert events[0].event_type == ModelExecutionEventType.MODEL_CALL
    assert events[0].subject == "deepseek-chat"
    assert events[0].metadata["provider"] == "deepseek"
    assert events[1].event_type == ModelExecutionEventType.TOOL_CALL
    assert events[1].subject == "web_search"


def test_model_execution_observer_records_permission_fallback_and_provider_events():
    observer = ModelExecutionObserver()

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
            status=ModelExecutionEventStatus.OK,
            provider_status="active",
            latency_ms=12.5,
        )
    )

    events = observer.snapshot()

    assert events[0].event_type == ModelExecutionEventType.PERMISSION_DECISION
    assert events[0].status == ModelExecutionEventStatus.ERROR
    assert events[0].subject == "RUN_SKILL"
    assert events[0].metadata["resource"] == "code_sandbox"
    assert events[0].metadata["allowed"] is False
    assert events[1].event_type == ModelExecutionEventType.FALLBACK
    assert events[1].subject == "local_fast"
    assert events[1].metadata["from_model_key"] == "remote_deep"
    assert events[2].event_type == ModelExecutionEventType.PROVIDER_VERIFY
    assert events[2].subject == "ollama"
    assert events[2].metadata["latency_ms"] == 12.5


def test_model_execution_observer_flush_resets_without_creating_legacy_jsonl(
    tmp_path: Path,
):
    observer = ModelExecutionObserver()
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="code_sandbox",
            status=ModelExecutionEventStatus.ERROR,
            metadata={"exit_code": 1},
        )
    )

    observer.flush("tick_001")

    assert observer.snapshot() == ()
    assert not (tmp_path / "runtime_events.jsonl").exists()


def test_call_llm_api_records_successful_model_call(monkeypatch: pytest.MonkeyPatch):
    observer = get_model_execution_observer()
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
    config = model_execution_config()
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
    assert events[-1].event_type == ModelExecutionEventType.MODEL_CALL
    assert events[-1].status == ModelExecutionEventStatus.OK
    assert events[-1].subject == "observed-model"
    assert events[-1].metadata["provider"] == "observed"
    assert events[-1].metadata["response_chars"] == len("observed response")


def test_call_llm_api_records_failed_model_call(monkeypatch: pytest.MonkeyPatch):
    observer = get_model_execution_observer()
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
    config = model_execution_config()
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
    assert events[-1].event_type == ModelExecutionEventType.MODEL_CALL
    assert events[-1].status == ModelExecutionEventStatus.ERROR
    assert events[-1].subject == "broken-model"
    assert events[-1].metadata["error_type"] == "RuntimeError"


def test_call_llm_api_result_preserves_native_calls_and_redacts_trace(
    monkeypatch: pytest.MonkeyPatch,
):
    dispatch_requests: list[dict[str, object]] = []

    def fake_dispatch(
        api_base: str,
        api_key: str,
        model_name: str,
        messages: list[dict[str, object]],
        temperature: float,
        max_tokens: int,
        provider: str,
        *,
        request_options: dict[str, object] | None = None,
        response_capture: dict[str, object] | None = None,
        return_metadata: bool = False,
    ):
        del api_base, api_key, model_name, messages, temperature, max_tokens, provider
        dispatch_requests.append(dict(request_options or {}))
        if response_capture is not None:
            response_capture["provider_marker"] = "captured"
        metadata = {
            "tool_called": True,
            "tool_calls": [
                {
                    "call_id": "call-1",
                    "name": "local_file",
                    "arguments": {
                        "operation": "read",
                        "resource_id": "notes.txt",
                    },
                }
            ],
        }
        result = ("", {"prompt_tokens": 2}, metadata)
        return result if return_metadata else result[:2]

    monkeypatch.setitem(API_DISPATCH, "chat_completions", fake_dispatch)
    config = model_execution_config()
    config.providers["observed_native"] = {
        "api_base": "https://api.observed.test",
        "api_key": "",
        "api_mode": "chat_completions",
    }
    trace: dict[str, object] = {}

    result = call_llm_api_result(
        config,
        "observed_native",
        "observed-model",
        [{"role": "user", "content": "read the file"}],
        0.0,
        128,
        request_options={
            "tool_definitions": [
                {
                    "type": "function",
                    "function": {
                        "name": "local_file",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "api_key": "super-secret",
        },
        response_capture=trace,
    )

    assert result.tool_calls[0].tool_key == "local_file"
    assert dispatch_requests[0]["tools"]
    assert trace["request"]["options"]["api_key"] == "[redacted]"
    assert trace["response"]["metadata"]["tool_called"] is True
    assert trace["response"]["metadata"]["tool_calls"][0]["name"] == "local_file"
    assert "super-secret" not in str(trace)


def test_tool_executor_records_tool_observation():
    observer = get_model_execution_observer()
    observer.reset()
    executor = ToolExecutor(
        ToolExecutionContext(
            allowed_tool_keys=("web_search",),
            search_plugin=FakeSearchPlugin(),
            permission_manager=FakePermissionManager(),
            observation_port=observer,
        )
    )

    result = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="ElfieNest")
    )

    events = observer.snapshot()
    observer.reset()
    assert result is not None
    assert events[-1].event_type == ModelExecutionEventType.TOOL_CALL
    assert events[-1].status == ModelExecutionEventStatus.OK
    assert events[-1].subject == "web_search"
    assert "query" not in events[-1].metadata
    assert events[-1].metadata["tool_call_index"] == 1
