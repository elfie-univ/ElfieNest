from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, Dict, List

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.executor import (
    FoodExecutionError,
    FoodExecutionResult,
    FoodExecutor,
    NoAvailableFoodError,
)
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID, FoodPackage
from ai_runtime.food.resolver import MainFoodSelection, resolve_main_food
from ai_runtime.food.store import FoodCatalog, FoodCatalogRepository
from ai_runtime.gateway.llm_api import call_llm_api
from ai_runtime.gateway.multimodal import assemble_multimodal_payload
from ai_runtime.gateway.request import (
    RuntimeRequest,
    RuntimeResult,
    StructuredGenerationMode,
    StructuredRuntimeCapabilities,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)
from ai_runtime.models.model_reference import parse_model_reference
from ai_runtime.safety.permissions import PermissionManager
from ai_runtime.tools.config import effective_tool_keys, load_tool_configs
from ai_runtime.usage.observer import (
    FallbackObservation,
    FoodDecisionObservation,
    RuntimeEventStatus,
    get_runtime_observer,
)
from infrastructure.persistence.data_home import get_runtime_config_paths
from infrastructure.tools.local_files import LocalFileAccessPlugin
from infrastructure.tools.search import WebSearchPlugin

logger = logging.getLogger("ai_runtime.gateway.agent")
MainFoodLoader = Callable[[str], MainFoodSelection]


class RuntimeAgent:
    """外包算力工厂底层 Agent - 拥有三轨自演化技能与原生多模态 Payload 组装能力"""

    def __init__(
        self,
        config: LLMRuntimeConfig = None,
        *,
        live_reload: bool = False,
        main_food_loader: MainFoodLoader | None = None,
        food_catalog_repository: FoodCatalogRepository | None = None,
    ):
        self.config = config or LLMRuntimeConfig()
        self._live_reload = live_reload
        self._main_food_loader = main_food_loader
        self.food_catalog_repository = food_catalog_repository
        self._config_mtimes_ns = self._config_mtimes()
        self._mount_runtime_dependencies()

    def _mount_runtime_dependencies(self) -> None:
        self.permission_manager = PermissionManager(self.config)

        self.search_plugin = WebSearchPlugin.from_runtime_policy(
            self.config.runtime_policy
        )
        tool_configs = load_tool_configs(self.config.runtime_policy)
        self._local_file_config = tool_configs["local_file"]
        self.file_access_plugin = None

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
            else ("web_search", "local_file")
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
        semantic_role: str = "primary",
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
            semantic_role=semantic_role,
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
        semantic_role: str = "primary",
        images: List[str] | None = None,
        audio: str | None = None,
    ) -> RuntimeResult:
        """返回完整执行结果，调用者仍只提交粮食语义和任务上下文。"""
        self._reload_config_if_changed()
        tools = effective_tool_keys(
            self.config.runtime_policy,
            tuple(allowed_skills or ()),
        )
        request = RuntimeRequest(
            prompt=prompt,
            energy=energy,
            task_complexity=task_complexity,
            allowed_tools=tools,
            elfie_id=elfie_id,
            elfie_config_dir=elfie_config_dir,
            food_key=food_key,
            semantic_role=semantic_role,
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
        food_unavailable: bool = False,
    ) -> StructuredRuntimeCapabilities:
        """Describe the primary role of the selected food package."""
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(
            catalog,
            food_key,
            unavailable=food_unavailable,
        )
        assignment = catalog.packages[selected_food].primary
        if assignment is None:
            raise NoAvailableFoodError("no_available_food")
        provider = self._provider_for_model(assignment.model)
        provider_config = self.config.providers.get(provider, {})
        native = (
            provider == "openai" or provider_config.get("catalog_id") == "openai_api"
        )
        return StructuredRuntimeCapabilities(
            provider=provider,
            model_key=assignment.model,
            supports_json_schema=native,
            supports_tool_calling=native,
            supports_json_mode=native,
            supports_plain_text=True,
            max_output_tokens=4096,
        )

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        """Execute exactly one structured generation using the selected mode."""
        self._reload_config_if_changed()
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(
            catalog,
            request.food_key,
            unavailable=request.food_unavailable,
        )
        attempts = [(selected_food, request.selected_mode)]
        if selected_food != FOOD_EMERGENCY_ID:
            emergency = catalog.packages.get(FOOD_EMERGENCY_ID)
            if emergency and self._package_usable(emergency):
                attempts.append((FOOD_EMERGENCY_ID, StructuredGenerationMode.JSON_TEXT))
        messages = (
            [message.model_dump(mode="python") for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        failures: list[str] = []
        for attempt_food, selected_mode in attempts:
            package = catalog.packages[attempt_food]
            assignment = package.primary
            if assignment is None:
                continue
            provider = self._provider_for_model(assignment.model)
            started = perf_counter()
            executor = self._food_executor(
                provider_options=self._structured_request_options(
                    request, selected_mode
                ),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                file_access_plugin=(
                    self._local_file_access(request.elfie_workspace)
                    if request.elfie_workspace
                    else None
                ),
            )
            try:
                execution = executor.execute(
                    package,
                    messages,
                    semantic_role="primary",
                    allowed_tools=tuple(request.allowed_tools),
                )
            except Exception as exc:
                failures.append(f"{attempt_food}: {exc}")
                continue
            return StructuredRuntimeResult(
                text=execution.text,
                selected_mode=selected_mode,
                provider=provider,
                model_key=execution.model,
                latency_ms=(perf_counter() - started) * 1000.0,
            )
        raise NoAvailableFoodError("no_available_food: " + " | ".join(failures))

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
        selection = self._main_food_selection(request)
        requested_food = selection.food_id or FOOD_COMMON_ID
        route = resolve_main_food(
            catalog,
            selection,
            is_usable=self._package_usable,
        )
        selected_food = route.food_id
        package = catalog.packages.get(selected_food)
        if package is None or package.primary is None:
            raise ValueError(f"粮食 '{selected_food}' 尚未配置")
        if not package.enabled or package.archived:
            raise NoAvailableFoodError("no_available_food", ())
        messages = (
            [dict(message) for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        executor = FoodExecutor(
            config=self.config,
            search_plugin=self.search_plugin,
            permission_manager=self.permission_manager,
            file_access_plugin=(
                self._local_file_access(request.elfie_config_dir)
                if request.elfie_config_dir
                else None
            ),
            model_caller=self._call_food_llm_api,
        )
        fallback_used = False
        failed_attempts: tuple[dict[str, str], ...] = ()
        try:
            execution = self._execute_package(
                executor,
                package,
                messages,
                request,
                tuple(request.allowed_tools),
            )
        except FoodExecutionError as exc:
            failed_attempts = exc.attempts
            emergency = catalog.packages.get(FOOD_EMERGENCY_ID)
            if (
                selected_food == FOOD_EMERGENCY_ID
                or emergency is None
                or not self._package_usable(emergency)
            ):
                raise NoAvailableFoodError(
                    "no_available_food",
                    failed_attempts,
                ) from exc
            execution = self._execute_package(
                executor,
                emergency,
                messages,
                request,
                tuple(request.allowed_tools),
            )
            selected_food = FOOD_EMERGENCY_ID
            fallback_used = True
        provider = (
            execution.model.split("/", 1)[0] if "/" in execution.model else "ollama"
        )
        clamped = route.used_emergency or selected_food != requested_food
        if fallback_used:
            selection_reason = "global_fallback_after_failure"
        elif clamped:
            selection_reason = "requested_food_unavailable"
        else:
            selection_reason = "requested_food_available"
        observer = get_runtime_observer()
        if fallback_used or (
            selected_food == FOOD_EMERGENCY_ID and requested_food != FOOD_EMERGENCY_ID
        ):
            previous_model = (
                failed_attempts[-1].get("model", "")
                if failed_attempts
                else (
                    catalog.packages[requested_food].primary.model
                    if requested_food in catalog.packages
                    and catalog.packages[requested_food].primary is not None
                    else ""
                )
            )
            observer.record_fallback(
                FallbackObservation(
                    from_model_key=previous_model,
                    from_provider=(
                        previous_model.split("/", 1)[0] if "/" in previous_model else ""
                    ),
                    to_model_key=execution.model,
                    to_provider=provider,
                    reason=(
                        "selected food execution failed"
                        if fallback_used
                        else "requested food unavailable"
                    ),
                )
            )
        observer.record_food_decision(
            FoodDecisionObservation(
                food_id=selected_food,
                status=RuntimeEventStatus.OK,
                requested_food_id=requested_food,
                semantic_role=request.semantic_role,
                model=execution.model,
                reason=selection_reason,
            )
        )
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
                "attempts": [*failed_attempts, *execution.attempts],
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

    def _execute_package(
        self,
        executor: FoodExecutor,
        package: FoodPackage,
        messages: list[dict[str, Any]],
        request: RuntimeRequest,
        allowed_tools: tuple[str, ...],
    ) -> FoodExecutionResult:
        return executor.execute(
            package,
            messages,
            allowed_tools=allowed_tools,
            max_loops=3,
            semantic_role=(request.semantic_role),
            images=request.images,
            audio=request.audio,
        )

    @staticmethod
    def _select_food_key(
        catalog: FoodCatalog,
        requested_food: str | None,
        *,
        unavailable: bool = False,
    ) -> str:
        return resolve_main_food(
            catalog,
            MainFoodSelection(requested_food, unavailable=unavailable),
            is_usable=RuntimeAgent._package_usable,
        ).food_id

    def _main_food_selection(self, request: RuntimeRequest) -> MainFoodSelection:
        if request.elfie_id and self._main_food_loader is not None:
            return self._main_food_loader(request.elfie_id)
        return MainFoodSelection(request.food_key)

    @staticmethod
    def _package_usable(package: FoodPackage) -> bool:
        if not package.enabled or package.archived or package.primary is None:
            return False
        health = project_food_health(package, query_model_evidence())
        if health.status not in {"healthy", "degraded"}:
            return False
        try:
            provider = RuntimeAgent._provider_for_model(package.primary.model)
            config = LLMRuntimeConfig.load()
            return provider in config.providers
        except Exception:
            return False

    def _food_executor(
        self,
        *,
        provider_options: Dict[str, Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
        file_access_plugin: Any | None = None,
    ) -> FoodExecutor:
        def caller(
            provider: str,
            model: str,
            messages: list[dict[str, Any]],
            _temperature: float,
            _max_tokens: int,
            options: dict[str, Any],
        ) -> str:
            return self._call_food_llm_api(
                provider,
                model,
                messages,
                temperature,
                max_tokens,
                {**options, **(provider_options or {})},
            )

        return FoodExecutor(
            config=self.config,
            search_plugin=self.search_plugin,
            permission_manager=self.permission_manager,
            file_access_plugin=file_access_plugin,
            model_caller=caller,
        )

    def _local_file_access(self, root: str) -> LocalFileAccessPlugin:
        return LocalFileAccessPlugin(
            root,
            max_read_bytes=int(self._local_file_config.get("max_read_bytes") or 65536),
            max_items=int(self._local_file_config.get("max_items") or 200),
        )

    def _load_food_catalog(self):
        if self.food_catalog_repository is None:
            raise RuntimeError("Runtime 未注入粮食数据库仓储")
        catalog = self.food_catalog_repository.load()
        if not catalog.recipes:
            raise RuntimeError(
                "正式粮食数据库不存在粮食配置，请先运行 setup/doctor 初始化"
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
