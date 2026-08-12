"""真实与 Mock Runtime 的调试适配层。"""

from __future__ import annotations

import json
import re
import time
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List

from devtools.elfie_lab.runtime_foods import (
    load_runtime_food_catalog,
    runtime_food_catalog_store,
)
from elfie.brain.food_port import FoodPackage
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from infrastructure.models.runtime_adapter import SerializedRuntimeAdapter
from infrastructure.models.runtime_agent import RuntimeAgent
from infrastructure.models.runtime_observations import get_runtime_observer
from infrastructure.models.runtime_ports import RuntimeAgentPorts
from infrastructure.persistence.configuration.secrets import resolve_secret
from infrastructure.persistence.food_evidence import query_model_evidence
from infrastructure.persistence.layout.data_home import get_elfie_developer_home
from infrastructure.tools.execution.config import effective_tool_keys, load_tool_configs
from infrastructure.tools.execution.loop import PortToolLoop
from infrastructure.tools.execution.permissions import PermissionManager
from infrastructure.tools.execution.skills_prompt import inject_skills_system_prompt
from infrastructure.tools.local_file.local_files import LocalFileAccessPlugin
from infrastructure.tools.port_adapter import ToolPortAdapter
from infrastructure.tools.web_search.search import WebSearchPlugin

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
        if self.food_key != "mock":
            return self.inner.capabilities()
        return ModelGenerationCapabilities(
            provider=self._provider_name(),
            model_key=self._model_name(2),
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=False,
            supports_plain_text=True,
            max_output_tokens=1024,
        )

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        if self.food_key != "mock":
            started = time.perf_counter()
            call: Dict[str, Any] = {
                "food_key": self.food_key,
                "energy": 100.0,
                "task_complexity": 2,
            }
            try:
                result = self.inner.generate(request)
                call.update(
                    {
                        "provider": result.provider,
                        "model": result.model_key,
                        "food_used": self.food_key,
                        "execution_stage": "primary",
                        "degraded": False,
                    }
                )
                return result
            except Exception as exc:
                call.update(
                    {
                        "provider": self._provider_name(),
                        "model": self._model_name(2),
                        "error": type(exc).__name__,
                    }
                )
                raise
            finally:
                call["duration_ms"] = round(
                    (time.perf_counter() - started) * 1000,
                    2,
                )
                self.calls.append(call)
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
        if self.food_key == "mock":
            del request
            return
        self.inner.abandon(request)

    @property
    def tool_port(self) -> Any:
        """Expose the selected runtime's semantic tools to Brain only."""
        return getattr(self.inner, "tool_port", None)

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
    if request.source_domain.value == "communication":
        intents = [
            {
                "type": "message",
                "intent_id": "mock-message",
                "channel_id": request.response_scope.channel_id,
                "conversation_id": request.response_scope.conversation_id,
                "content": speech,
                **common,
            }
        ]
    else:
        intents = [
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
        ]
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
            "intents": intents,
        },
        ensure_ascii=False,
    )


class FoodRuntimeAgent:
    """让精灵实验通过粮食语义调用 Runtime。"""

    def __init__(
        self,
        runtime: Any,
        food_key: str,
        package: FoodPackage,
        brain_tool_port: Any = None,
    ):
        self.runtime = runtime
        self.config = runtime.config
        self.food_key = food_key
        self.selected_model = package.primary.model if package.primary else ""
        self.selected_provider = _provider_from_model(self.selected_model)
        self.last_result = None
        self._brain_tool_port = brain_tool_port
        self._adapter = SerializedRuntimeAdapter(
            runtime,
            food_key_resolver=lambda: self.food_key,
        )

    def capabilities(self) -> ModelGenerationCapabilities:
        return self._adapter.capabilities()

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        result = self._adapter.generate(request)
        self.selected_model = result.model_key
        self.selected_provider = result.provider
        return result

    def abandon(self, request: ModelGenerationRequest) -> None:
        self._adapter.abandon(request)

    @property
    def tool_port(self) -> Any:
        """Expose the runtime-injected semantic tool view to Brain."""
        return self._brain_tool_port or getattr(self.runtime, "tool_port", None)

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


def create_runtime(
    food_key: str,
    config_dir: str | None = None,
    workspace_resolver: Callable[[str | None], Path | None] | None = None,
) -> TracingRuntimeAgent:
    normalized = food_key.lower().strip()
    if normalized == "mock":
        return TracingRuntimeAgent(MockRuntimeAgent(), "mock")

    from devtools.runtime_lab import RuntimeLabConfigStore

    store = RuntimeLabConfigStore(config_dir or default_runtime_config_dir())
    config = store.load_runtime_config()
    food_store = runtime_food_catalog_store(store)
    catalog = load_runtime_food_catalog(store, food_store)
    package = catalog.packages.get(normalized)
    if package is None:
        raise ValueError(f"Runtime 粮食目录中不存在粮食: {normalized}")

    agent = RuntimeAgent(
        config,
        ports=_runtime_agent_ports(store),
        food_catalog_repository=food_store,
    )
    brain_tool_port = ToolPortAdapter.from_runtime_config(
        config,
        observation_port=get_runtime_observer(),
        allowed_tool_keys=("web_search", "local_file"),
        workspace_resolver=workspace_resolver,
    )
    food_agent = FoodRuntimeAgent(
        agent,
        normalized,
        package,
        brain_tool_port=brain_tool_port,
    )
    return TracingRuntimeAgent(food_agent, normalized)


def _runtime_agent_ports(store: Any) -> RuntimeAgentPorts:
    observer = get_runtime_observer()
    tool_config_loader = partial(load_tool_configs, secret_resolver=resolve_secret)

    def build_permission_manager(
        config: Any, observation_port: Any
    ) -> PermissionManager:
        return PermissionManager(config, observation_port)

    def build_file_access(
        root: str, max_read_bytes: int, max_items: int
    ) -> LocalFileAccessPlugin:
        return LocalFileAccessPlugin(
            root,
            max_read_bytes=max_read_bytes,
            max_items=max_items,
        )

    return RuntimeAgentPorts(
        observer=observer,
        config_paths=lambda: (store.config_path, store.env_path),
        search_factory=partial(
            WebSearchPlugin.from_runtime_policy,
            secret_resolver=resolve_secret,
        ),
        permission_factory=build_permission_manager,
        tool_config_loader=tool_config_loader,
        effective_tool_keys=partial(
            effective_tool_keys, secret_resolver=resolve_secret
        ),
        file_access_factory=build_file_access,
        model_evidence_source=query_model_evidence,
        tool_loop_factory=lambda tool_port, allowed, scope: PortToolLoop(
            tool_port,
            allowed_tool_keys=allowed,
            scope_id=scope,
        ),
        prompt_injector=inject_skills_system_prompt,
        runtime_config_loader=store.load_runtime_config,
    )


def default_runtime_config_dir() -> str:
    """返回 Elfie Lab 专属的开发 Runtime Lab 根目录。"""
    return str(get_elfie_developer_home() / "runtime_lab")


def _provider_from_model(model_ref: str) -> str:
    if not model_ref:
        return ""
    return model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"
