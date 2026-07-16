from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Dict, List

from runtime.config import LLMRuntimeConfig
from runtime.food.bootstrap import build_compatibility_food_catalog
from runtime.food.elfie_policy import (
    ElfieFoodPolicy,
    load_elfie_food_policy,
    resolve_food_selection,
)
from runtime.food.executor import FoodExecutor
from runtime.food.models import FIXED_FOOD_KINDS
from runtime.food.store import FoodCatalogStore
from runtime.gateway.generation import GenerationRuntime, generate_text
from runtime.gateway.llm_api import call_llm_api
from runtime.gateway.model_guard import ensure_model_ready
from runtime.gateway.multimodal import assemble_multimodal_payload
from runtime.gateway.request import RuntimeRequest, RuntimeResult
from runtime.gateway.skills_prompt import inject_skills_system_prompt
from runtime.gateway.streaming import RuntimeStreamRequest, stream_runtime_response
from runtime.models.registry import ModelRegistry
from runtime.policy.food_policy import RuntimeTaskType, task_type_from_prompt
from runtime.policy.router import ModelRouter
from runtime.providers.ollama import OllamaManager
from runtime.safety.permissions import PermissionManager
from runtime.storage.data_home import get_config_path
from runtime.tools.code import CodeSandboxPlugin
from runtime.tools.config import enabled_tool_keys, load_tool_configs
from runtime.tools.local_files import LocalFileAccessPlugin
from runtime.tools.search import WebSearchPlugin
from runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin

logger = logging.getLogger("runtime.gateway.agent")


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
        self._config_mtime_ns = self._config_mtime()
        self._mount_runtime_dependencies()

    def _mount_runtime_dependencies(self) -> None:

        # 1. 注册核心设施
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

        # 3. 智能路由模块挂载
        self.router = ModelRouter(self.config)
        self._last_fallback: Dict[str, Any] | None = None
        self.food_catalog_store = FoodCatalogStore()

    @staticmethod
    def _config_mtime() -> int | None:
        try:
            return get_config_path().stat().st_mtime_ns
        except OSError:
            return None

    def _reload_config_if_changed(self) -> None:
        if not self._live_reload:
            return
        current_mtime = self._config_mtime()
        if current_mtime == self._config_mtime_ns:
            return
        self.config = LLMRuntimeConfig.load()
        self._config_mtime_ns = current_mtime
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
        # 旧版调用方通常通过 patch ``router.route_request``/``generate`` 做
        # 单元测试或集成适配。保留这条兼容桥，不让粮食重构改变旧接口语义。
        if "generate" in self.__dict__:
            return self._ask_legacy_compat(prompt, energy, task_complexity, list(tools))
        return self.run_with_food(
            prompt=prompt,
            food_key=None,
            energy=energy,
            task_complexity=task_complexity,
            allowed_skills=list(tools),
        ).text

    def _ask_legacy_compat(
        self,
        prompt: str,
        energy: float,
        task_complexity: int,
        allowed_skills: List[str],
    ) -> str:
        mode, _decision = self.router.route_request(prompt, energy, task_complexity)
        model_key = "local_fast" if mode == "local" else "remote_deep"
        return self.generate(
            model_key=model_key,
            messages=[{"role": "user", "content": prompt}],
            allowed_skills=allowed_skills,
        )

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
        tools = tuple(
            tool for tool in (allowed_skills or ()) if tool in enabled_tools
        )
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
        if (
            "generate" in self.__dict__
            or (
                "route_request" in getattr(self.router, "__dict__", {})
                and not getattr(self, "_in_food_request", False)
            )
        ):
            return self._think_legacy_compat(request)
        if request.food_key is None:
            request = replace(request, food_key=self._infer_food_key(request))
        return self._think_with_food(request)

    def _think_legacy_compat(self, request: RuntimeRequest) -> RuntimeResult:
        metadata = dict(request.metadata)
        task_type = metadata.get("task_type")
        routed_mode = None
        if "route_request" in getattr(self.router, "__dict__", {}):
            routed_mode, _ = self.router.route_request(
                request.prompt, request.energy, request.task_complexity
            )
        if routed_mode == "remote":
            model_key = "remote_deep"
        elif routed_mode == "local":
            model_key = "local_fast"
        elif task_type == RuntimeTaskType.REASONING.value or request.task_complexity >= self.config.complexity_threshold_deep:
            model_key = "remote_deep"
        elif request.energy < self.config.energy_threshold_fast:
            model_key = "remote_deep"
        else:
            model_key = "local_fast"
        messages = (
            [dict(message) for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        text = self.generate(
            model_key=model_key,
            messages=messages,
            images=list(request.images) or None,
            audio=request.audio,
            allowed_skills=list(request.allowed_tools),
        )
        fallback = self._last_fallback
        result_model_key = fallback.get("to_model_key", model_key) if fallback else model_key
        return RuntimeResult(
            text=text,
            mode="local" if result_model_key == "local_fast" else "remote",
            model_key=result_model_key,
            decision={
                "mode": "local" if model_key == "local_fast" else "remote",
                "food_policy": {
                    "task_type": task_type,
                    "group_key": "premium" if model_key == "remote_deep" else "standard",
                },
                **({"fallback": fallback} if fallback else {}),
            },
            degraded=bool(fallback),
        )

    def _think_with_food(self, request: RuntimeRequest) -> RuntimeResult:
        catalog = self._load_food_catalog()
        if request.elfie_id:
            policy = load_elfie_food_policy(
                request.elfie_id,
                request.elfie_config_dir,
            )
        else:
            policy = ElfieFoodPolicy(
                elfie_id="",
                default_food=request.food_key or "standard",
                allowed_foods=tuple(FIXED_FOOD_KINDS),
                fallback_food="coarse",
            )
        selection = resolve_food_selection(policy, request.food_key, catalog)
        recipe = catalog.recipes.get(selection.actual_food)
        if recipe is None:
            raise ValueError(f"粮食 '{selection.actual_food}' 尚未配置")
        messages = (
            [dict(message) for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        execution = FoodExecutor(
            config=self.config,
            search_plugin=self.search_plugin,
            sandbox_plugin=self.sandbox_plugin,
            skills_evolution_plugin=self.skills_evolution_plugin,
            permission_manager=self.permission_manager,
            file_access_plugin=self.file_access_plugin,
            model_caller=self._call_food_llm_api,
        ).execute(
            recipe,
            messages,
            allowed_tools=request.allowed_tools,
            max_loops=3,
            prefer_deep=(
                selection.clamped and selection.requested_food in {"focus", "premium"}
            ),
            images=request.images,
            audio=request.audio,
        )
        provider = (
            execution.model.split("/", 1)[0] if "/" in execution.model else "ollama"
        )
        return RuntimeResult(
            text=execution.text,
            mode="local" if provider == "ollama" else "remote",
            model_key=execution.model,
            decision={
                "food": {
                    "requested": selection.requested_food,
                    "actual": selection.actual_food,
                    "reason": selection.reason,
                },
                "scene": request.scene,
            },
            degraded=execution.technical_fallback_used or selection.clamped,
            food_requested=selection.requested_food,
            food_used=selection.actual_food,
            execution_stage=execution.execution_stage,
            actual_model=execution.model,
            food_clamped=selection.clamped,
        )

    def _load_food_catalog(self):
        catalog = self.food_catalog_store.load()
        return (
            catalog
            if catalog.recipes
            else build_compatibility_food_catalog(self.config)
        )

    def _infer_food_key(self, request: RuntimeRequest) -> str:
        metadata = dict(request.metadata)
        raw_task_type = metadata.get("task_type")
        task_type = (
            RuntimeTaskType(raw_task_type)
            if isinstance(raw_task_type, str)
            and raw_task_type in {item.value for item in RuntimeTaskType}
            else task_type_from_prompt(request.prompt)
        )
        if request.images or request.audio:
            return "vision"
        if request.energy < self.config.energy_threshold_fast:
            return "coarse"
        if request.task_complexity >= self.config.complexity_threshold_deep:
            return "focus"
        default_food = {
            RuntimeTaskType.CHAT: "standard",
            RuntimeTaskType.REASONING: "focus",
            RuntimeTaskType.VISION: "vision",
            RuntimeTaskType.CODE: "tool",
            RuntimeTaskType.ORGANIZE: "focus",
        }[task_type]
        raw_routes = self.config.runtime_policy.get("task_routes", {})
        if isinstance(raw_routes, dict):
            configured = raw_routes.get(task_type.value)
            if isinstance(configured, str) and configured in FIXED_FOOD_KINDS:
                return configured
        return default_food

    def generate(
        self,
        model_key: str,
        messages: List[Dict[str, Any]],
        images: List[str] = None,
        audio: str = None,
        temperature: float = None,
        max_tokens: int = None,
        allowed_skills: List[str] = None,
        max_loops: int = 1,
        owner_token: str = None,
    ) -> str:
        """
        高度可控的多模态大模型 generate 接口
        :param model_key: 算力套餐中的 Model Key (如 "local_fast", "remote_deep")
        :param messages: 完整的对话上下文历史
        :param images: 待处理图片本地绝对路径列表
        :param audio: 待处理音频本地绝对路径
        :param temperature: 随机温度 (不传使用 config 默认值)
        :param max_tokens: 最大Token限制
        :param allowed_skills: 允许调用的技能列表 (如 ["web_search", "code_sandbox", "skills_evolution"])
        :param max_loops: 多轮推理循环迭代上限
        :param owner_token: 特权令牌，用于 N3 重构时代谢技能
        :return: 大模型最终的纯文本响应
        """
        return generate_text(
            self._generation_runtime(),
            model_key=model_key,
            messages=messages,
            images=images,
            audio=audio,
            temperature=temperature,
            max_tokens=max_tokens,
            allowed_skills=allowed_skills,
            max_loops=max_loops,
            owner_token=owner_token,
        )

    def generate_stream(
        self,
        model_key: str,
        messages: List[Dict[str, Any]],
        images: List[str] = None,
        audio: str = None,
        temperature: float = None,
        max_tokens: int = None,
        allowed_skills: List[str] = None,
        max_loops: int = 1,
        owner_token: str = None,
    ):
        """SSE 流式生成 — yield 文本 chunk，流结束后检查 skill tag

        与 generate() 完全独立，不影响同步调用链。
        使用 httpx.stream 进行 SSE 流式响应。

        ⚠️ 注意：流式模式下不支持多轮推理循环（max_loops 固定为 1），
        因为流式响应需要实时 yield，无法进行工具回调后的二次请求。
        """
        target = ensure_model_ready(
            model_key, self.registry, self.ollama_manager, images, audio
        )
        model_name = target.model_name
        provider = target.provider

        # 拷贝 messages 避免外部入参篡改
        local_messages = [dict(m) for m in messages]

        # 3. 拼装多模态媒体载荷至最新的一条 User Message
        if images or audio:
            local_messages = self._assemble_multimodal_payload(
                local_messages, images, audio, provider
            )

        # 4. 根据允许的技能，动态向上下文顶部注入防幻觉指令规约
        if allowed_skills:
            local_messages = self._inject_skills_system_prompt(
                local_messages, allowed_skills
            )

        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        yield from stream_runtime_response(
            RuntimeStreamRequest(
                config=self.config,
                provider=provider,
                model_name=model_name,
                messages=local_messages,
                temperature=temp,
                max_tokens=tokens,
                allowed_skills=tuple(allowed_skills or ()),
            )
        )

    def _assemble_multimodal_payload(
        self,
        messages: List[Dict[str, Any]],
        images: List[str] = None,
        audio: str = None,
        provider: str = "ollama",
    ) -> List[Dict[str, Any]]:
        return assemble_multimodal_payload(messages, images, audio, provider)

    def _inject_skills_system_prompt(
        self, messages: List[Dict[str, Any]], allowed_skills: List[str]
    ) -> List[Dict[str, Any]]:
        return inject_skills_system_prompt(messages, allowed_skills)

    def _call_llm_api(
        self,
        provider: str,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        return call_llm_api(
            self.config, provider, model_name, messages, temperature, max_tokens
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

    def _generation_runtime(self) -> GenerationRuntime:
        return GenerationRuntime(
            config=self.config,
            registry=self.registry,
            ollama_manager=self.ollama_manager,
            search_plugin=self.search_plugin,
            sandbox_plugin=self.sandbox_plugin,
            skills_evolution_plugin=self.skills_evolution_plugin,
            permission_manager=self.permission_manager,
            call_llm_api=self._call_llm_api,
            set_fallback_info=self._set_fallback_info,
            file_access_plugin=self.file_access_plugin,
        )

    def _set_fallback_info(self, fallback_info: Dict[str, Any] | None) -> None:
        self._last_fallback = fallback_info
