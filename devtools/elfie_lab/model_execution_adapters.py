"""真实与 Mock 模型执行器的调试适配层。"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List

from devtools.elfie_lab.model_execution_foods import (
    ElfieLabModelEnvironment,
    default_model_execution_config_dir,
    load_model_execution_food_catalog,
    model_execution_food_catalog_store,
)
from elfie.brain.reasoning.food_port import FoodPackage
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from infrastructure.models.model_execution_adapter import (
    SerializedModelExecutionAdapter,
)
from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_observations import (
    get_model_execution_observer,
)
from infrastructure.models.model_execution_ports import ModelExecutionAgentPorts
from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults
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


class MockModelExecutionAgent:
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


class TracingModelExecutionAgent:
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
            execution_result = getattr(self.inner, "last_result", None)
            if execution_result is not None:
                call.update(
                    {
                        "food_used": execution_result.food_used,
                        "execution_stage": execution_result.execution_stage,
                        "degraded": execution_result.degraded,
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
        if (
            self.food_key == "mock"
            and request.response_schema is not None
            and request.response_schema.name == "MemoryProjection"
        ):
            # The offline agent has no semantic extractor. Return an empty,
            # source-safe projection so the event node and Episode evidence can
            # still be committed through the same typed maintenance contract.
            text = _mock_memory_projection_json()
        else:
            speech = self.ask(request.user_prompt, energy=100.0, task_complexity=2)
            text = (
                _mock_decision_json(request, speech)
                if self.food_key == "mock"
                else speech
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
        """Expose the selected model execution's semantic tools to Brain only."""
        return getattr(self.inner, "tool_port", None)

    def _model_name(self, task_complexity: int) -> str:
        if self.food_key == "mock":
            return "elfie-mock"
        if hasattr(self.inner, "selected_model"):
            return str(self.inner.selected_model)
        return "model_environment-selected"

    def _provider_name(self) -> str:
        if self.food_key == "mock":
            return "mock"
        return str(getattr(self.inner, "selected_provider", "model_execution_router"))


def _mock_memory_projection_json() -> str:
    """Return a valid conservative MemoryProjection for offline runs."""
    return json.dumps(
        {"nodes": [], "mentions": [], "assertions": []},
        ensure_ascii=False,
    )


def _mock_decision_json(request: ModelGenerationRequest, speech: str) -> str:
    intent_suffix = str(request.turn_id)
    common = {
        "cause_event_ids": [str(item) for item in request.cause_event_ids],
        "dependency_ids": [],
        "deadline": request.deadline.isoformat(),
        "cancel_policy": "always",
    }
    intents: list[dict[str, object]]
    if request.source_domain.value == "communication":
        intents = [
            {
                "type": "message",
                "intent_id": f"mock-message:{intent_suffix}",
                "channel_id": request.response_scope.channel_id,
                "conversation_id": request.response_scope.conversation_id,
                "content": speech,
                **common,
            }
        ]
        if "提醒" in request.user_prompt or "稍后" in request.user_prompt:
            wake_at = request.created_at.timestamp() + 30
            activity_deadline = request.created_at.timestamp() + 300
            intents.append(
                {
                    "type": "activity",
                    "intent_id": f"mock-activity-intent:{intent_suffix}",
                    "draft": {
                        "schema_version": 1,
                        "activity_id": "mock-activity",
                        "goal": "在约定时间提醒主人",
                        "success_criteria": "通过当前已授权会话发送提醒",
                        "steps": [
                            {
                                "step_id": "mock-activity-step",
                                "ordinal": 0,
                                "kind": "communication",
                                "operation": "send_message",
                                "deadline": datetime.fromtimestamp(
                                    activity_deadline, timezone.utc
                                ).isoformat(),
                                "scope": {
                                    "external_domain": "communication",
                                    "target_actor_id": "elfie-lab-owner",
                                    "channel_id": request.response_scope.channel_id,
                                    "conversation_id": request.response_scope.conversation_id,
                                    "capability_revision": request.capability_revision,
                                    "allowed_operations": ["send_message"],
                                    "expires_at": datetime.fromtimestamp(
                                        activity_deadline, timezone.utc
                                    ).isoformat(),
                                },
                                "retry_limit": 1,
                            }
                        ],
                        "cause_event_ids": [
                            str(item) for item in request.cause_event_ids
                        ],
                        "idempotency_key": f"mock-activity:{request.turn_id}",
                        "created_at": request.created_at.isoformat(),
                        "deadline": datetime.fromtimestamp(
                            activity_deadline, timezone.utc
                        ).isoformat(),
                        "wake_at": datetime.fromtimestamp(
                            wake_at, timezone.utc
                        ).isoformat(),
                        "estimated_budget": 1.0,
                    },
                    **common,
                }
            )
    elif (
        request.response_scope.external_domain is not None
        and request.response_scope.external_domain.value == "communication"
    ):
        intents = [
            {
                "type": "message",
                "intent_id": f"mock-internal-message:{intent_suffix}",
                "channel_id": request.response_scope.channel_id,
                "conversation_id": request.response_scope.conversation_id,
                "content": speech,
                **common,
            }
        ]
    elif (
        request.response_scope.external_domain is not None
        and request.response_scope.external_domain.value == "nervous_system"
    ):
        intents = [
            {
                "type": "speech",
                "intent_id": f"mock-internal-speech:{intent_suffix}",
                "text": speech,
                **common,
            },
            {
                "type": "motion",
                "intent_id": f"mock-internal-motion:{intent_suffix}",
                "motion": "nod_head",
                "target": None,
                **common,
            },
        ]
    else:
        recovery_trigger = "internal:motivation" in request.user_prompt
        offline_trigger = "internal:consolidation" in request.user_prompt
        intents = [
            {
                "type": "noop",
                "intent_id": f"mock-noop:{intent_suffix}",
                "reason": (
                    "恢复驱力已处理：保持安静并等待能量恢复"
                    if recovery_trigger
                    else "离线整理已完成：只更新记忆，不产生外部动作"
                    if offline_trigger
                    else "internal trigger has no external scope"
                ),
                "cancel_policy": "if_not_started",
                **{
                    key: value
                    for key, value in common.items()
                    if key != "cancel_policy"
                },
            }
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


class FoodModelExecutionAgent:
    """让精灵实验通过粮食语义调用模型执行器。"""

    def __init__(
        self,
        model_environment: Any,
        food_key: str,
        package: FoodPackage,
        brain_tool_port: Any = None,
    ):
        self.model_environment = model_environment
        self.config = model_environment.config
        self.food_key = food_key
        self.selected_model = package.primary.model if package.primary else ""
        self.selected_provider = _provider_from_model(self.selected_model)
        self.last_result = None
        self._brain_tool_port = brain_tool_port
        self._adapter = SerializedModelExecutionAdapter(
            model_environment,
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
        """Expose the model-execution-injected semantic tool view to Brain."""
        return self._brain_tool_port or getattr(
            self.model_environment, "tool_port", None
        )

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        result = self.model_environment.run_with_food(
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


def create_model_execution(
    food_key: str,
    config_dir: str | None = None,
    workspace_resolver: Callable[[str | None], Path | None] | None = None,
) -> TracingModelExecutionAgent:
    normalized = food_key.lower().strip()
    if normalized == "mock":
        return TracingModelExecutionAgent(MockModelExecutionAgent(), "mock")

    model_environment = ElfieLabModelEnvironment(
        config_dir or default_model_execution_config_dir()
    )
    config = model_environment.load_model_execution_config()
    food_store = model_execution_food_catalog_store(model_environment)
    catalog = load_model_execution_food_catalog(model_environment, food_store)
    package = catalog.packages.get(normalized)
    if package is None:
        raise ValueError(f"模型执行粮食目录中不存在粮食: {normalized}")

    agent = ModelExecutionAgent(
        config,
        ports=_model_execution_agent_ports(model_environment),
        food_catalog_repository=food_store,
    )
    brain_tool_port = ToolPortAdapter.from_model_execution_config(
        config,
        observation_port=get_model_execution_observer(),
        tool_config_loader=partial(
            load_tool_configs,
            defaults=load_tool_defaults(),
            secret_resolver=model_environment.resolve_secret,
        ),
        allowed_tool_keys=("web_search", "local_file"),
        workspace_resolver=workspace_resolver,
    )
    food_agent = FoodModelExecutionAgent(
        agent,
        normalized,
        package,
        brain_tool_port=brain_tool_port,
    )
    return TracingModelExecutionAgent(food_agent, normalized)


def _model_execution_agent_ports(
    model_environment: ElfieLabModelEnvironment,
) -> ModelExecutionAgentPorts:
    observer = get_model_execution_observer()
    tool_defaults = load_tool_defaults()
    tool_config_loader = partial(
        load_tool_configs,
        defaults=tool_defaults,
        secret_resolver=model_environment.resolve_secret,
    )

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

    return ModelExecutionAgentPorts(
        observer=observer,
        config_paths=model_environment.config_paths,
        search_factory=partial(
            WebSearchPlugin.from_model_execution_policy,
            defaults=tool_defaults,
            secret_resolver=model_environment.resolve_secret,
        ),
        permission_factory=build_permission_manager,
        tool_config_loader=tool_config_loader,
        effective_tool_keys=partial(
            effective_tool_keys,
            defaults=tool_defaults,
            secret_resolver=model_environment.resolve_secret,
        ),
        file_access_factory=build_file_access,
        model_evidence_source=model_environment.model_evidence,
        tool_loop_factory=lambda tool_port, allowed, scope: PortToolLoop(
            tool_port,
            allowed_tool_keys=allowed,
            scope_id=scope,
        ),
        prompt_injector=inject_skills_system_prompt,
        model_execution_config_loader=model_environment.load_model_execution_config,
    )


def _provider_from_model(model_ref: str) -> str:
    if not model_ref:
        return ""
    return model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"
