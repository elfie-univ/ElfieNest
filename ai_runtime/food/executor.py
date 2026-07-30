"""Execute one food package role and its ordered internal fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext
from ai_runtime.gateway.multimodal import assemble_multimodal_payload
from ai_runtime.gateway.skills_prompt import inject_skills_system_prompt
from ai_runtime.models.model_reference import ModelReferenceError, parse_model_reference


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


class NoAvailableFoodError(FoodExecutionError):
    code = "no_available_food"


class FoodExecutor:
    def __init__(
        self,
        *,
        config: LLMRuntimeConfig,
        search_plugin: Any,
        permission_manager: Any,
        file_access_plugin: Any,
        model_caller: Callable[
            [str, str, list[dict[str, Any]], float, int, dict[str, Any]], str
        ],
    ) -> None:
        self.config = config
        self.search_plugin = search_plugin
        self.permission_manager = permission_manager
        self.file_access_plugin = file_access_plugin
        self.model_caller = model_caller

    def execute(
        self,
        package: FoodPackage,
        messages: list[dict[str, Any]],
        *,
        semantic_role: str = "primary",
        allowed_tools: tuple[str, ...] = (),
        max_loops: int = 3,
        images: tuple[str, ...] = (),
        audio: str | None = None,
    ) -> FoodExecutionResult:
        selected = package.assignment_for(semantic_role)
        stage = semantic_role
        if selected is None and semantic_role != "primary":
            selected = package.primary
            stage = "primary"
        candidates: list[tuple[str, ModelAssignment]] = []
        if selected is not None:
            candidates.append((stage, selected))
        candidates.extend(
            (f"fallback_{index}", assignment)
            for index, assignment in enumerate(package.fallback, 1)
            if assignment != selected
        )
        attempts: list[dict[str, str]] = []
        for candidate_stage, assignment in candidates:
            try:
                text = self._execute_assignment(
                    assignment,
                    [dict(message) for message in messages],
                    allowed_tools=allowed_tools,
                    max_loops=max_loops,
                    images=images,
                    audio=audio,
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
                    technical_fallback_used=candidate_stage.startswith("fallback_"),
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
        assignment: ModelAssignment,
        messages: list[dict[str, Any]],
        *,
        allowed_tools: tuple[str, ...],
        max_loops: int,
        images: tuple[str, ...],
        audio: str | None,
    ) -> str:
        try:
            reference = parse_model_reference(assignment.model)
        except ModelReferenceError as exc:
            raise FoodExecutionError(str(exc)) from exc
        connection_id = reference.connection_id
        provider_config = self.config.providers.get(connection_id, {})
        api_mode = str(provider_config.get("api_mode") or "")
        if api_mode != "ollama" and not provider_config.get("api_key"):
            raise FoodExecutionError(f"Provider 连接 '{connection_id}' 没有可用密钥")
        if images or audio:
            messages = assemble_multimodal_payload(
                messages,
                list(images),
                audio,
                "ollama" if api_mode == "ollama" else connection_id,
            )
        if allowed_tools:
            messages = inject_skills_system_prompt(messages, list(allowed_tools))
        loop = RuntimeToolLoop(
            ToolLoopContext(
                allowed_skills=allowed_tools,
                search_plugin=self.search_plugin,
                permission_manager=self.permission_manager,
                file_access_plugin=self.file_access_plugin,
            )
        )

        def invoke(loop_messages: list[dict[str, Any]]) -> str:
            return self.model_caller(
                connection_id,
                reference.model_id,
                loop_messages,
                0.7,
                1500,
                {},
            )

        return loop.run(messages, max_loops, invoke)
