"""真实与 Mock Runtime 的调试适配层。"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from ai_runtime.food.models import FoodPackage
from ai_runtime.storage.data_home import get_elfie_developer_home
from devtools.elfie_lab.runtime_foods import (
    load_runtime_food_catalog,
    runtime_food_catalog_store,
)
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
)


def redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("<redacted>", result)
    return result


class MockRuntimeAgent:
    """可离线、可预期的开发者模式。"""

    class MockConfig:
        providers = {
            "ollama": {"api_key": "", "api_base": "mock://local"},
            "openai": {"api_key": "", "api_base": ""},
            "deepseek": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
        }

    config = MockConfig()

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        match = re.search(r"【主人发送的信息】:\s*(.+?)\n\n", prompt, re.DOTALL)
        message = match.group(1).strip() if match else "这件事"
        if len(message) > 28:
            message = message[:28] + "…"
        return f"我有好好听到你说\u201c{message}\u201d哒。"


class TracingRuntimeAgent:
    """记录模型调用，同时保持 `ask` 协议兼容。"""

    def __init__(self, inner: Any, food_key: str):
        self.inner = inner
        self.food_key = food_key
        self.config = inner.config
        self.calls: List[Dict[str, Any]] = []

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        started = time.perf_counter()
        call: Dict[str, Any] = {
            "food_key": self.food_key,
            "prompt": redact_text(prompt),
            "energy": energy,
            "task_complexity": task_complexity,
            "provider": self._provider_name(),
            "model": self._model_name(task_complexity),
        }
        try:
            response = self.inner.ask(prompt, energy, task_complexity)
            call["provider"] = self._provider_name()
            call["model"] = self._model_name(task_complexity)
            runtime_result = getattr(self.inner, "last_result", None)
            if runtime_result is not None:
                call.update(
                    {
                        "food_used": runtime_result.food_used,
                        "execution_stage": runtime_result.execution_stage,
                        "degraded": runtime_result.degraded,
                    }
                )
            call["response"] = redact_text(str(response))
            return response
        except Exception as exc:
            call["provider"] = self._provider_name()
            call["model"] = self._model_name(task_complexity)
            call["error"] = type(exc).__name__
            raise
        finally:
            call["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.calls.append(call)

    def capabilities(self) -> ModelGenerationCapabilities:
        structured_mock = self.food_key == "mock"
        return ModelGenerationCapabilities(
            provider=self._provider_name(),
            model_key=self._model_name(2),
            supports_json_schema=structured_mock,
            supports_tool_calling=False,
            supports_json_mode=False,
            supports_plain_text=True,
            max_output_tokens=1024,
        )

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        speech = self.ask(request.user_prompt, energy=100.0, task_complexity=2)
        text = (
            _mock_decision_json(request, speech) if self.food_key == "mock" else speech
        )
        return ModelGenerationResult(
            text=text,
            selected_mode=(
                StructuredOutputMode.JSON_SCHEMA
                if self.food_key == "mock"
                else StructuredOutputMode.JSON_TEXT
            ),
            provider=self._provider_name(),
            model_key=self._model_name(2),
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        """Detach the Lab request; the temporary adapter owns no call gate."""
        del request

    def _model_name(self, task_complexity: int) -> str:
        if self.food_key == "mock":
            return "elfie-mock"
        if hasattr(self.inner, "selected_model"):
            return str(self.inner.selected_model)
        return "runtime-selected"

    def _provider_name(self) -> str:
        if self.food_key == "mock":
            return "mock"
        return str(getattr(self.inner, "selected_provider", "runtime_router"))


def _mock_decision_json(request: ModelGenerationRequest, speech: str) -> str:
    common = {
        "cause_event_ids": [str(item) for item in request.cause_event_ids],
        "dependency_ids": [],
        "deadline": request.deadline.isoformat(),
        "cancel_policy": "always",
    }
    return json.dumps(
        {
            "schema_version": 1,
            "plan_id": "mock-plan",
            "turn_id": str(request.turn_id),
            "frame_id": str(request.frame_id),
            "context_revision": request.context_revision,
            "capability_revision": request.capability_revision,
            "created_at": request.created_at.isoformat(),
            "deadline": request.deadline.isoformat(),
            "cause_event_ids": [str(item) for item in request.cause_event_ids],
            "intents": [
                {
                    "type": "speech",
                    "intent_id": "mock-speech",
                    "text": speech,
                    **common,
                },
                {
                    "type": "motion",
                    "intent_id": "mock-motion",
                    "motion": "nod_head",
                    "target": None,
                    **common,
                },
            ],
        },
        ensure_ascii=False,
    )


class FoodRuntimeAgent:
    """让精灵实验通过粮食语义调用 Runtime。"""

    def __init__(self, runtime: Any, food_key: str, package: FoodPackage):
        self.runtime = runtime
        self.config = runtime.config
        self.food_key = food_key
        self.selected_model = package.primary.model if package.primary else ""
        self.selected_provider = _provider_from_model(self.selected_model)
        self.last_result = None

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        result = self.runtime.run_with_food(
            prompt=prompt,
            food_key=self.food_key,
            energy=energy,
            task_complexity=task_complexity,
            allowed_skills=[],
        )
        self.last_result = result
        self.selected_model = str(result.actual_model or result.model_key)
        self.selected_provider = _provider_from_model(self.selected_model)
        return result.text


def create_runtime(food_key: str, config_dir: str | None = None) -> TracingRuntimeAgent:
    normalized = food_key.lower().strip()
    if normalized == "mock":
        return TracingRuntimeAgent(MockRuntimeAgent(), "mock")

    from ai_runtime import RuntimeAgent
    from devtools.runtime_lab import RuntimeLabConfigStore

    store = RuntimeLabConfigStore(config_dir or default_runtime_config_dir())
    config = store.load_runtime_config()
    food_store = runtime_food_catalog_store(store)
    catalog = load_runtime_food_catalog(store, food_store)
    package = catalog.packages.get(normalized)
    if package is None:
        raise ValueError(f"Runtime 粮食目录中不存在粮食: {normalized}")

    agent = RuntimeAgent(config)
    agent.food_catalog_store = food_store
    food_agent = FoodRuntimeAgent(agent, normalized, package)
    return TracingRuntimeAgent(food_agent, normalized)


def default_runtime_config_dir() -> str:
    """返回 Elfie Lab 专属的开发 Runtime Lab 根目录。"""
    return str(get_elfie_developer_home() / "runtime_lab")


def _provider_from_model(model_ref: str) -> str:
    if not model_ref:
        return ""
    return model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"
