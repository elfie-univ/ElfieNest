from dataclasses import dataclass
from typing import Any

import pytest

from runtime.gateway.agent import RuntimeAgent
from runtime.gateway.fallback import (
    FallbackPlan,
    MissingLocalModelError,
    build_fallback_prompt,
    resolve_fallback_plan,
)
from runtime.gateway.request import RuntimeRequest


@dataclass
class FakeRegistry:
    local_info: dict[str, Any]

    def get_model_info(self, model_key: str) -> dict[str, Any]:
        assert model_key == "local_fast"
        return self.local_info


@dataclass
class FakeOllamaManager:
    has_required_model: bool = True

    def has_model(self, model_name: str) -> bool:
        return self.has_required_model


def test_resolve_fallback_plan_uses_local_fast_when_model_is_installed():
    plan = resolve_fallback_plan(
        failed_model_key="remote_deep",
        failed_provider="openai",
        failure=RuntimeError("remote failed"),
        registry=FakeRegistry(
            {
                "name": "qwen3.5:0.8b",
                "provider": "ollama",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
        ),
        ollama_manager=FakeOllamaManager(),
    )

    assert plan == FallbackPlan(
        model_key="local_fast",
        model_name="qwen3.5:0.8b",
        provider="ollama",
        reason="openai 调用失败，已切换到本地 Ollama 兜底模型 qwen3.5:0.8b。",
    )


def test_resolve_fallback_plan_reports_missing_local_model():
    with pytest.raises(MissingLocalModelError) as exc_info:
        resolve_fallback_plan(
            failed_model_key="remote_deep",
            failed_provider="openai",
            failure=RuntimeError("remote failed"),
            registry=FakeRegistry(
                {
                    "name": "qwen3.5:0.8b",
                    "provider": "ollama",
                    "is_vision": False,
                    "is_audio": False,
                    "active": True,
                }
            ),
            ollama_manager=FakeOllamaManager(has_required_model=False),
        )

    assert "qwen3.5:0.8b" in str(exc_info.value)
    assert "ollama pull qwen3.5:0.8b" in str(exc_info.value)


def test_build_fallback_prompt_preserves_original_request_and_explains_degradation():
    prompt = build_fallback_prompt(
        messages=[{"role": "user", "content": "帮我检查系统状态"}],
        reason="openai 调用失败，已切换到本地 Ollama 兜底模型 qwen3.5:0.8b。",
    )

    assert "本地兜底模式" in prompt
    assert "帮我检查系统状态" in prompt
    assert "openai 调用失败" in prompt


def test_runtime_agent_think_marks_result_degraded_after_remote_fallback():
    agent = RuntimeAgent()

    agent.router.route_request = lambda prompt, energy, task_complexity: (
        "remote",
        {"mode": "remote"},
    )
    agent.registry.get_model_info = lambda model_key: {
        "remote_deep": {
            "name": "gpt-4",
            "provider": "openai",
            "is_vision": False,
            "is_audio": False,
            "active": True,
        },
        "local_fast": {
            "name": "qwen3.5:0.8b",
            "provider": "ollama",
            "is_vision": False,
            "is_audio": False,
            "active": True,
        },
    }[model_key]
    agent.ollama_manager.ensure_service_started = lambda: True
    agent.ollama_manager.has_model = lambda model_name: model_name == "qwen3.5:0.8b"

    calls = []

    def fake_call_llm_api(provider, model_name, messages, temperature, max_tokens):
        calls.append((provider, model_name, messages))
        if provider == "openai":
            raise RuntimeError("remote unavailable")
        return "本地兜底回复"

    agent._call_llm_api = fake_call_llm_api

    result = agent.think(RuntimeRequest(prompt="现在还能工作吗？"))

    assert result.text == "本地兜底回复"
    assert result.degraded is True
    assert result.model_key == "local_fast"
    assert result.decision["fallback"]["from_model_key"] == "remote_deep"
    assert calls[1][0] == "ollama"
    assert "本地兜底模式" in calls[1][2][0]["content"]
