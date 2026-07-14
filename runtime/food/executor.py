"""粮食配方的正式 Runtime Agent 执行器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from runtime.config import LLMRuntimeConfig
from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext
from runtime.gateway.multimodal import assemble_multimodal_payload
from runtime.gateway.skills_prompt import inject_skills_system_prompt


@dataclass(frozen=True)
class FoodExecutionResult:
    text: str
    model: str
    execution_stage: str
    technical_fallback_used: bool


class FoodExecutionError(RuntimeError):
    pass


class FoodExecutor:
    def __init__(
        self,
        *,
        config: LLMRuntimeConfig,
        search_plugin: Any,
        sandbox_plugin: Any,
        skills_evolution_plugin: Any,
        permission_manager: Any,
        file_access_plugin: Any,
        model_caller: Callable[
            [str, str, list[dict[str, Any]], float, int, dict[str, Any]], str
        ],
    ) -> None:
        self.config = config
        self.search_plugin = search_plugin
        self.sandbox_plugin = sandbox_plugin
        self.skills_evolution_plugin = skills_evolution_plugin
        self.permission_manager = permission_manager
        self.file_access_plugin = file_access_plugin
        self.model_caller = model_caller

    def execute(
        self,
        recipe: FoodRecipe,
        messages: list[dict[str, Any]],
        *,
        allowed_tools: tuple[str, ...] = (),
        max_loops: int = 3,
        prefer_deep: bool = False,
        images: tuple[str, ...] = (),
        audio: str | None = None,
    ) -> FoodExecutionResult:
        candidates: list[tuple[str, ExecutionProfile]] = []
        if prefer_deep and recipe.deep is not None:
            candidates.append(("deep", recipe.deep))
        candidates.append(("primary", recipe.primary))
        candidates.extend(
            (f"fallback_{index}", profile)
            for index, profile in enumerate(recipe.technical_fallbacks, 1)
        )
        failures: list[str] = []
        for stage, profile in candidates:
            if not profile.model:
                failures.append(f"{stage}: 模型未配置")
                continue
            try:
                text = self._execute_profile(
                    profile,
                    [dict(message) for message in messages],
                    allowed_tools=allowed_tools,
                    max_loops=max_loops,
                    images=images,
                    audio=audio,
                )
                return FoodExecutionResult(
                    text=text,
                    model=profile.model,
                    execution_stage=stage,
                    technical_fallback_used=stage.startswith("fallback_"),
                )
            except Exception as exc:
                failures.append(f"{stage} ({profile.model}): {exc}")
        raise FoodExecutionError(
            f"粮食 '{recipe.key}' 的所有执行模型均失败：" + " | ".join(failures)
        )

    def _execute_profile(
        self,
        profile: ExecutionProfile,
        messages: list[dict[str, Any]],
        *,
        allowed_tools: tuple[str, ...],
        max_loops: int,
        images: tuple[str, ...],
        audio: str | None,
    ) -> str:
        provider, model = _parse_model_ref(profile.model)
        provider_config = self.config.providers.get(provider, {})
        if provider != "ollama" and not provider_config.get("api_key"):
            raise FoodExecutionError(f"Provider '{provider}' 没有可用密钥")
        tools = tuple(tool for tool in profile.tools if tool in allowed_tools)
        if images or audio:
            messages = assemble_multimodal_payload(
                messages,
                list(images),
                audio,
                provider,
            )
        if tools:
            messages = inject_skills_system_prompt(messages, list(tools))
        loop = RuntimeToolLoop(
            ToolLoopContext(
                allowed_skills=tools,
                search_plugin=self.search_plugin,
                sandbox_plugin=self.sandbox_plugin,
                skills_evolution_plugin=self.skills_evolution_plugin,
                permission_manager=self.permission_manager,
                file_access_plugin=self.file_access_plugin,
            )
        )

        def invoke(loop_messages: list[dict[str, Any]]) -> str:
            return self.model_caller(
                provider,
                model,
                loop_messages,
                profile.temperature,
                profile.max_tokens,
                dict(profile.provider_options),
            )

        return loop.run(messages, max_loops, invoke)


def _parse_model_ref(model_ref: str) -> tuple[str, str]:
    if "/" not in model_ref:
        return "ollama", model_ref
    return tuple(model_ref.split("/", 1))  # type: ignore[return-value]
