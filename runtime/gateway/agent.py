import logging
from typing import Any, Dict, List

from runtime.config import LLMRuntimeConfig
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
from runtime.models.groups import load_model_groups
from runtime.models.registry import ModelRegistry
from runtime.policy.food_policy import load_food_policy, resolve_food_policy
from runtime.policy.router import ModelRouter
from runtime.providers.ollama import OllamaManager
from runtime.safety.permissions import PermissionManager
from runtime.tools.code import CodeSandboxPlugin
from runtime.tools.local_files import LocalFileAccessPlugin
from runtime.tools.search import WebSearchPlugin
from runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin

logger = logging.getLogger("runtime.gateway.agent")


class RuntimeAgent:
    """外包算力工厂底层 Agent - 拥有三轨自演化技能与原生多模态 Payload 组装能力"""

    def __init__(self, config: LLMRuntimeConfig = None):
        self.config = config or LLMRuntimeConfig()

        # 1. 注册核心设施
        self.registry = ModelRegistry(self.config)
        self.ollama_manager = OllamaManager(self.config)
        self.permission_manager = PermissionManager(self.config)

        # 2. 挂载能力插件
        self.search_plugin = WebSearchPlugin()
        self.sandbox_plugin = CodeSandboxPlugin()
        self.skills_evolution_plugin = SkillsSelfEvolutionPlugin(
            self.permission_manager
        )
        self.file_access_plugin = LocalFileAccessPlugin()

        # 3. 智能路由模块挂载
        self.router = ModelRouter(self.config)
        self._last_fallback: Dict[str, Any] | None = None
        self.food_catalog_store = FoodCatalogStore()

    def ask(
        self,
        prompt: str,
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] = None,
    ) -> str:
        """
        向后兼容旧的脑皮层 ask 接口，内部自动调度 ModelRouter 进行智能模型与算力路由
        """
        tools = (
            tuple(allowed_skills)
            if allowed_skills is not None
            else ("web_search", "local_file", "code_sandbox", "skills_evolution")
        )
        return self.think(
            RuntimeRequest(
                prompt=prompt,
                energy=energy,
                task_complexity=task_complexity,
                allowed_tools=tools,
            )
        ).text

    def ask_with_food(
        self,
        prompt: str,
        food_key: str,
        elfie_id: str | None = None,
        scene: str = "chat",
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] | None = None,
    ) -> str:
        """粮食语义接口；目录尚未生成时自动兼容旧路由。"""
        catalog = self.food_catalog_store.load()
        if not catalog.recipes:
            return self.ask(
                prompt,
                energy=energy,
                task_complexity=task_complexity,
                allowed_skills=allowed_skills,
            )
        tools = tuple(allowed_skills or ())
        return self.think(
            RuntimeRequest(
                prompt=prompt,
                energy=energy,
                task_complexity=task_complexity,
                allowed_tools=tools,
                elfie_id=elfie_id,
                food_key=food_key,
                scene=scene,
            )
        ).text

    def think(self, request: RuntimeRequest) -> RuntimeResult:
        if request.food_key is not None:
            return self._think_with_food(request)
        metadata = dict(request.metadata)
        task_type = metadata.get("task_type")
        if task_type is not None:
            available_model_keys = set(self.registry.list_available_models())
            runtime_policy = self.config.runtime_policy
            food_decision = resolve_food_policy(
                str(task_type),
                available_model_keys,
                food_policy=load_food_policy(runtime_policy),
                model_groups=load_model_groups(runtime_policy),
            )
            model_key = food_decision.model_key
            mode = "local" if model_key.startswith("local_") else "remote"
            decision = {
                "mode": mode,
                "food_policy": food_decision.to_dict(),
            }
        else:
            mode, decision = self.router.route_request(
                request.prompt,
                request.energy,
                request.task_complexity,
            )
            if mode == "local":
                model_key = "local_fast"
            else:
                model_key = "remote_deep"

        logger.info(
            f"🔮 [智能算力分配] 路由模式为 '{mode}'，最终分发至 model_key: '{model_key}'"
        )

        # 3. 组装单轮单用户消息 payload
        messages = (
            [dict(message) for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )

        allowed_skills = list(request.allowed_tools)

        # 4. 调用高弹性 generate 接口，限制最长自进化/防幻觉多轮迭代上限为 3 次
        self._last_fallback = None
        text = self.generate(
            model_key=model_key,
            messages=messages,
            allowed_skills=allowed_skills,
            max_loops=3,
        )
        fallback_info = self._last_fallback
        result_model_key = (
            fallback_info["to_model_key"] if fallback_info is not None else model_key
        )
        result_decision = dict(decision)
        if fallback_info is not None:
            result_decision["fallback"] = fallback_info
        return RuntimeResult(
            text=text,
            mode=mode,
            model_key=result_model_key,
            decision=result_decision,
            degraded=fallback_info is not None,
        )

    def _think_with_food(self, request: RuntimeRequest) -> RuntimeResult:
        catalog = self.food_catalog_store.load()
        if request.elfie_id:
            policy = load_elfie_food_policy(request.elfie_id)
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
        admin_token: str = None,
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
        :param admin_token: 特权令牌，用于 N3 重构时代谢技能
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
            admin_token=admin_token,
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
        admin_token: str = None,
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
