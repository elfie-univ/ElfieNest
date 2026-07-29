from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, List

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.executor import (
    FoodExecutionError,
    FoodExecutionResult,
    FoodExecutor,
)
from ai_runtime.food.models import FoodRecipe
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.gateway.llm_api import call_llm_api
from ai_runtime.gateway.model_guard import ensure_model_ready
from ai_runtime.gateway.multimodal import assemble_multimodal_payload
from ai_runtime.gateway.request import (
    RuntimeRequest,
    RuntimeResult,
    StructuredGenerationMode,
    StructuredRuntimeCapabilities,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)
from ai_runtime.gateway.skills_prompt import inject_skills_system_prompt
from ai_runtime.gateway.streaming import RuntimeStreamRequest, stream_runtime_response
from ai_runtime.models.model_reference import parse_model_reference
from ai_runtime.models.registry import ModelRegistry
from ai_runtime.providers.ollama import OllamaManager
from ai_runtime.safety.permissions import PermissionManager
from ai_runtime.storage.data_home import get_runtime_config_paths
from ai_runtime.tools.code import CodeSandboxPlugin
from ai_runtime.tools.config import enabled_tool_keys, load_tool_configs
from ai_runtime.tools.local_files import LocalFileAccessPlugin
from ai_runtime.tools.search import WebSearchPlugin
from ai_runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin

logger = logging.getLogger("ai_runtime.gateway.agent")


class RuntimeAgent:
    """外包算力工厂底层 Agent - 拥有三轨自演化技能与原生多模态 Payload 组装能力"""

    def __init__(
        self,
        config: LLMRuntimeConfig = None,
        *,
        live_reload: bool = False,
    ):
        self.config = config or LLMRuntimeConfig()
        self._live_reload = live_reload
        self._config_mtimes_ns = self._config_mtimes()
        self._mount_runtime_dependencies()

    def _mount_runtime_dependencies(self) -> None:
        self.registry = ModelRegistry(self.config)
        self.ollama_manager = OllamaManager(self.config)
        self.permission_manager = PermissionManager(self.config)

        # 2. 挂载能力插件
        tool_configs = load_tool_configs(self.config.runtime_policy)
        self.search_plugin = WebSearchPlugin.from_runtime_policy(
            self.config.runtime_policy
        )
        self.sandbox_plugin = CodeSandboxPlugin(
            timeout_seconds=float(
                tool_configs["code_sandbox"].get("timeout_seconds") or 5.0
            )
        )
        self.skills_evolution_plugin = SkillsSelfEvolutionPlugin(
            self.permission_manager
        )
        self.file_access_plugin = LocalFileAccessPlugin(
            root=str(tool_configs["local_file"].get("root") or "") or None
        )

        self.food_catalog_store = FoodCatalogStore()

    @staticmethod
    def _config_mtimes() -> tuple[int | None, ...]:
        mtimes: list[int | None] = []
        for path in get_runtime_config_paths():
            try:
                mtimes.append(path.stat().st_mtime_ns)
            except OSError:
                mtimes.append(None)
        return tuple(mtimes)

    def _reload_config_if_changed(self) -> None:
        if not self._live_reload:
            return
        current_mtimes = self._config_mtimes()
        if current_mtimes == self._config_mtimes_ns:
            return
        self.config = LLMRuntimeConfig.load()
        self._config_mtimes_ns = current_mtimes
        self._mount_runtime_dependencies()

    def ask(
        self,
        prompt: str,
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] = None,
    ) -> str:
        """兼容文本接口；内部只转换成粮食请求，不再直接选择模型。"""
        tools = (
            tuple(allowed_skills)
            if allowed_skills is not None
            else ("web_search", "local_file", "code_sandbox", "skills_evolution")
        )
        return self.run_with_food(
            prompt=prompt,
            food_key=None,
            energy=energy,
            task_complexity=task_complexity,
            allowed_skills=list(tools),
        ).text

    def ask_with_food(
        self,
        prompt: str,
        food_key: str | None,
        elfie_id: str | None = None,
        elfie_config_dir: str | None = None,
        scene: str = "chat",
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] | None = None,
        images: List[str] | None = None,
        audio: str | None = None,
    ) -> str:
        """粮食语义文本接口。"""
        return self.run_with_food(
            prompt=prompt,
            food_key=food_key,
            elfie_id=elfie_id,
            elfie_config_dir=elfie_config_dir,
            scene=scene,
            energy=energy,
            task_complexity=task_complexity,
            allowed_skills=allowed_skills,
            images=images,
            audio=audio,
        ).text

    def run_with_food(
        self,
        *,
        prompt: str,
        food_key: str | None,
        elfie_id: str | None = None,
        elfie_config_dir: str | None = None,
        scene: str = "chat",
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] | None = None,
        images: List[str] | None = None,
        audio: str | None = None,
    ) -> RuntimeResult:
        """返回完整执行结果，调用者仍只提交粮食语义和任务上下文。"""
        self._reload_config_if_changed()
        enabled_tools = set(enabled_tool_keys(self.config.runtime_policy))
        tools = tuple(tool for tool in (allowed_skills or ()) if tool in enabled_tools)
        request = RuntimeRequest(
            prompt=prompt,
            energy=energy,
            task_complexity=task_complexity,
            allowed_tools=tools,
            elfie_id=elfie_id,
            elfie_config_dir=elfie_config_dir,
            food_key=food_key,
            scene=scene,
            images=tuple(images or ()),
            audio=audio,
        )
        self._in_food_request = True
        try:
            return self.think(request)
        finally:
            self._in_food_request = False

    def think(self, request: RuntimeRequest) -> RuntimeResult:
        self._reload_config_if_changed()
        return self._think_with_food(request)

    def structured_capabilities(
        self,
        food_key: str | None = None,
    ) -> StructuredRuntimeCapabilities:
        """Describe the primary role of the selected food package."""
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(catalog, food_key)
        profile = catalog.recipes[selected_food].primary
        provider = self._provider_for_model(profile.model)
        provider_config = self.config.providers.get(provider, {})
        native = (
            provider == "openai" or provider_config.get("catalog_id") == "openai_api"
        )
        return StructuredRuntimeCapabilities(
            provider=provider,
            model_key=profile.model,
            supports_json_schema=native,
            supports_tool_calling=native,
            supports_json_mode=native,
            supports_plain_text=True,
            max_output_tokens=profile.max_tokens,
        )

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        """Execute exactly one structured generation using the selected mode."""
        self._reload_config_if_changed()
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(catalog, request.food_key)
        attempts = [
            (
                selected_food,
                catalog.recipes[selected_food].primary,
                request.selected_mode,
            )
        ]
        fallback_food = catalog.fallback_food
        if (
            fallback_food
            and fallback_food != selected_food
            and fallback_food in catalog.recipes
        ):
            attempts.append(
                (
                    fallback_food,
                    catalog.recipes[fallback_food].primary,
                    StructuredGenerationMode.JSON_TEXT,
                )
            )
        messages = (
            [message.model_dump(mode="python") for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        failures: list[str] = []
        for attempt_food, profile, selected_mode in attempts:
            provider = self._provider_for_model(profile.model)
            model_name = self._model_name(profile.model)
            started = perf_counter()
            try:
                text = self._call_food_llm_api(
                    provider,
                    model_name,
                    messages,
                    request.temperature,
                    min(request.max_tokens, profile.max_tokens),
                    self._structured_request_options(request, selected_mode),
                )
            except Exception as exc:
                failures.append(f"{attempt_food}: {exc}")
                continue
            return StructuredRuntimeResult(
                text=text,
                selected_mode=selected_mode,
                provider=provider,
                model_key=profile.model,
                latency_ms=(perf_counter() - started) * 1000.0,
            )
        raise RuntimeError(
            "结构化生成的主粮与全局保底粮均不可用：" + " | ".join(failures)
        )

    @staticmethod
    def _provider_for_model(model_key: str) -> str:
        return parse_model_reference(model_key).provider_id

    @staticmethod
    def _model_name(model_key: str) -> str:
        return parse_model_reference(model_key).model_id

    @staticmethod
    def _structured_request_options(
        request: StructuredRuntimeRequest,
        selected_mode: StructuredGenerationMode,
    ) -> Dict[str, Any]:
        if selected_mode is StructuredGenerationMode.JSON_SCHEMA:
            return {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.response_schema_name,
                        "schema": dict(request.response_schema),
                        "strict": True,
                    },
                }
            }
        if selected_mode is StructuredGenerationMode.TOOL_CALL:
            return {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": request.response_schema_name,
                            "parameters": dict(request.response_schema),
                        },
                    }
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": request.response_schema_name},
                },
            }
        return {}

    def _think_with_food(self, request: RuntimeRequest) -> RuntimeResult:
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(catalog, request.food_key)
        requested_food = request.food_key or selected_food
        recipe = catalog.recipes[selected_food]
        messages = (
            [dict(message) for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        executor = FoodExecutor(
            config=self.config,
            search_plugin=self.search_plugin,
            sandbox_plugin=self.sandbox_plugin,
            skills_evolution_plugin=self.skills_evolution_plugin,
            permission_manager=self.permission_manager,
            file_access_plugin=self.file_access_plugin,
            model_caller=self._call_food_llm_api,
        )
        fallback_used = False
        try:
            execution = self._execute_recipe(executor, recipe, messages, request)
        except FoodExecutionError:
            fallback_food = catalog.fallback_food
            if (
                not fallback_food
                or fallback_food == selected_food
                or fallback_food not in catalog.recipes
            ):
                raise
            execution = self._execute_recipe(
                executor,
                catalog.recipes[fallback_food],
                messages,
                request,
            )
            selected_food = fallback_food
            fallback_used = True
        provider = (
            execution.model.split("/", 1)[0] if "/" in execution.model else "ollama"
        )
        clamped = selected_food != requested_food
        if fallback_used:
            selection_reason = "global_fallback_after_failure"
        elif clamped:
            selection_reason = "requested_food_unavailable"
        else:
            selection_reason = "requested_food_available"
        return RuntimeResult(
            text=execution.text,
            mode="local" if provider == "ollama" else "remote",
            model_key=execution.model,
            decision={
                "food": {
                    "requested": requested_food,
                    "actual": selected_food,
                    "reason": selection_reason,
                },
                "scene": request.scene,
            },
            degraded=execution.technical_fallback_used or clamped,
            food_requested=requested_food,
            food_used=selected_food,
            execution_stage=(
                f"global_fallback:{execution.execution_stage}"
                if fallback_used
                else execution.execution_stage
            ),
            actual_model=execution.model,
            food_clamped=clamped,
        )

    def _execute_recipe(
        self,
        executor: FoodExecutor,
        recipe: FoodRecipe,
        messages: list[dict[str, Any]],
        request: RuntimeRequest,
    ) -> FoodExecutionResult:
        return executor.execute(
            recipe,
            messages,
            allowed_tools=request.allowed_tools,
            max_loops=3,
            prefer_deep=(
                request.task_complexity >= self.config.complexity_threshold_deep
            ),
            prefer_vision=bool(request.images or request.audio),
            images=request.images,
            audio=request.audio,
        )

    @staticmethod
    def _select_food_key(
        catalog: FoodCatalog,
        requested_food: str | None,
    ) -> str:
        for food_key in (
            requested_food,
            catalog.default_food,
            catalog.fallback_food,
            *catalog.recipes,
        ):
            if food_key and food_key in catalog.recipes:
                return food_key
        raise RuntimeError("正式粮食配置中没有可执行的套餐")

    def _load_food_catalog(self):
        catalog = self.food_catalog_store.load()
        if not catalog.recipes:
            raise RuntimeError(
                f"正式粮食配置 {self.food_catalog_store.path.name} "
                "不存在或为空，请先运行 setup/doctor 初始化"
            )
        return catalog

    def _assemble_multimodal_payload(
        self,
        messages: List[Dict[str, Any]],
        images: List[str] | None = None,
        audio: str | None = None,
        provider: str = "ollama",
    ) -> List[Dict[str, Any]]:
        """供粮食执行器适配层复用的多模态载荷组装。"""
        return assemble_multimodal_payload(messages, images, audio, provider)

    def _inject_skills_system_prompt(
        self, messages: List[Dict[str, Any]], allowed_skills: List[str]
    ) -> List[Dict[str, Any]]:
        """供粮食执行器适配层复用的技能提示注入。"""
        return inject_skills_system_prompt(messages, allowed_skills)

    def _call_llm_api(
        self,
        provider: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """执行底层 Provider 调用；正式请求由 FoodExecutor 统一调度。"""
        return call_llm_api(
            self.config, provider, model_name, messages, temperature, max_tokens
        )

    def generate_stream(
        self,
        model_key: str,
        messages: List[Dict[str, Any]],
        images: List[str] | None = None,
        audio: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        allowed_skills: List[str] | None = None,
    ):
        """底层流式传输适配；同步业务请求必须使用粮食执行链。"""
        target = ensure_model_ready(
            model_key, self.registry, self.ollama_manager, images, audio
        )
        local_messages = [dict(message) for message in messages]
        if images or audio:
            local_messages = self._assemble_multimodal_payload(
                local_messages, images, audio, target.provider
            )
        if allowed_skills:
            local_messages = self._inject_skills_system_prompt(
                local_messages, allowed_skills
            )
        yield from stream_runtime_response(
            RuntimeStreamRequest(
                config=self.config,
                provider=target.provider,
                model_name=target.model_name,
                messages=local_messages,
                temperature=(
                    self.config.temperature if temperature is None else temperature
                ),
                max_tokens=(
                    self.config.max_tokens if max_tokens is None else max_tokens
                ),
                allowed_skills=tuple(allowed_skills or ()),
            )
        )

    def _call_food_llm_api(
        self,
        provider: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        request_options: Dict[str, Any],
    ) -> str:
        return call_llm_api(
            self.config,
            provider,
            model_name,
            messages,
            temperature,
            max_tokens,
            request_options=request_options,
        )
