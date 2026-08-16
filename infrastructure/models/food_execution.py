"""Execute one Elfie Food package role through model and tool Adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from elfie.brain.reasoning.food_port import (
    FoodAssignment,
    FoodPackage,
)
from elfie.brain.reasoning.tool_port import ToolPort
from infrastructure.models.inference.multimodal import assemble_multimodal_payload
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_observations import (
    ModelCallContext,
    scoped_model_call_context,
)
from infrastructure.models.model_execution_ports import ModelExecutionToolLoopPort
from infrastructure.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)


@dataclass(frozen=True)
class FoodExecutionResult:
    text: str
    model: str
    execution_stage: str
    technical_fallback_used: bool
    attempts: tuple[dict[str, str], ...] = ()


class FoodExecutionError(RuntimeError):
    def __init__(self, message: str, attempts: tuple[dict[str, str], ...] = ()) -> None:
        super().__init__(message)
        self.attempts = attempts


class FoodExecutor:
    def __init__(
        self,
        *,
        config: ModelExecutionConfig,
        tool_port: ToolPort,
        model_caller: Callable[
            [str, str, list[dict[str, Any]], float, int, dict[str, Any]], str
        ],
        tool_loop_factory: Callable[
            [ToolPort, tuple[str, ...], Optional[str]], ModelExecutionToolLoopPort
        ],
        prompt_injector: Callable[
            [list[dict[str, Any]], list[str]], list[dict[str, Any]]
        ],
    ) -> None:
        self.config = config
        self.tool_port = tool_port
        self.model_caller = model_caller
        self.tool_loop_factory = tool_loop_factory
        self.prompt_injector = prompt_injector

    def execute(
        self,
        package: FoodPackage,
        messages: list[dict[str, Any]],
        *,
        semantic_role: str = "primary",
        allowed_tools: tuple[str, ...] = (),
        max_loops: int = 3,
        allow_fallback: bool = True,
        images: tuple[str, ...] = (),
        audio: str | None = None,
        scope_id: str | None = None,
    ) -> FoodExecutionResult:
        selected = package.assignment_for(semantic_role)
        stage = semantic_role
        if selected is None and semantic_role != "primary":
            selected = package.primary
            stage = "primary"
        candidates: list[tuple[str, FoodAssignment]] = []
        if selected is not None:
            candidates.append((stage, selected))
        if (
            allow_fallback
            and package.fallback is not None
            and package.fallback != selected
        ):
            candidates.append(("fallback", package.fallback))
        attempts: list[dict[str, str]] = []
        for candidate_stage, assignment in candidates:
            try:
                text = self._execute_assignment(
                    assignment,
                    [dict(message) for message in messages],
                    food_id=package.key,
                    semantic_role=semantic_role,
                    route_stage=candidate_stage,
                    allowed_tools=allowed_tools,
                    max_loops=max_loops,
                    images=images,
                    audio=audio,
                    scope_id=scope_id,
                )
                attempts.append(
                    {
                        "food_id": package.key,
                        "stage": candidate_stage,
                        "model": assignment.model,
                        "result": "passed",
                    }
                )
                return FoodExecutionResult(
                    text=text,
                    model=assignment.model,
                    execution_stage=candidate_stage,
                    technical_fallback_used=candidate_stage == "fallback",
                    attempts=tuple(attempts),
                )
            except Exception as exc:
                attempts.append(
                    {
                        "food_id": package.key,
                        "stage": candidate_stage,
                        "model": assignment.model,
                        "result": type(exc).__name__,
                    }
                )
        raise FoodExecutionError(
            f"粮食 '{package.key}' 没有可执行模型",
            tuple(attempts),
        )

    def _execute_assignment(
        self,
        assignment: FoodAssignment,
        messages: list[dict[str, Any]],
        *,
        food_id: str,
        semantic_role: str,
        route_stage: str,
        allowed_tools: tuple[str, ...],
        max_loops: int,
        images: tuple[str, ...],
        audio: str | None,
        scope_id: str | None,
    ) -> str:
        try:
            reference = parse_model_reference(assignment.model)
        except ModelReferenceError as exc:
            raise FoodExecutionError(str(exc)) from exc
        connection_id = reference.connection_id
        provider_config = self.config.providers.get(connection_id, {})
        api_mode = str(provider_config.get("api_mode") or "")
        # When model_caller is provided (e.g., for testing), bypass API key check
        if (
            api_mode != "ollama"
            and not provider_config.get("api_key")
            and self.model_caller is None
        ):
            raise FoodExecutionError(f"Provider 连接 '{connection_id}' 没有可用密钥")
        if images or audio:
            messages = assemble_multimodal_payload(
                messages,
                list(images),
                audio,
                "ollama" if api_mode == "ollama" else connection_id,
            )
        available_tools = set(self.tool_port.available_tool_keys())
        effective_tools = tuple(
            tool
            for tool in allowed_tools
            if tool in available_tools
            and (tool != "local_file" or scope_id is not None)
        )
        if effective_tools:
            self.prompt_injector(messages, list(effective_tools))
        loop = self.tool_loop_factory(self.tool_port, effective_tools, scope_id)

        def invoke(loop_messages: list[dict[str, Any]]) -> str:
            with scoped_model_call_context(
                ModelCallContext(
                    connection_id=connection_id,
                    endpoint_model_id=reference.model_id,
                    food_id=food_id,
                    semantic_role=semantic_role,
                    route_stage=route_stage,
                    workload_kind="production",
                    scope_id=scope_id,
                )
            ):
                return self.model_caller(
                    connection_id,
                    reference.model_id,
                    loop_messages,
                    0.7,
                    1500,
                    {},
                )

        return loop.run(messages, max_loops, invoke)
