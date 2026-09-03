from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any, Callable, Dict, List, cast

from pydantic import JsonValue

from elfie.brain.reasoning.food_port import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodCatalog,
    FoodPackage,
    FoodPort,
    MainFoodSelection,
    NoAvailableFoodError,
    is_food_executable,
    resolve_main_food,
)
from elfie.brain.reasoning.skill_port import SkillLoadCall
from elfie.brain.reasoning.tool_port import (
    ToolDefinition,
    ToolKey,
    ToolPort,
    ToolRequest,
    ToolResult,
)
from elfie.message_types import ErrorInfo
from infrastructure.models.capabilities import resolve_model_capability_profile
from infrastructure.models.food_execution import (
    FoodExecutionError,
    FoodExecutionResult,
    FoodExecutor,
)
from infrastructure.models.inference.llm_api import (
    LLMCallResult,
    call_llm_api,
    call_llm_api_result,
)
from infrastructure.models.inference.multimodal import assemble_multimodal_payload
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_contracts import (
    ModelExecutionRequest,
    ModelExecutionResult,
    StructuredGenerationMode,
    StructuredModelExecutionCapabilities,
    StructuredModelExecutionRequest,
    StructuredModelExecutionResult,
)
from infrastructure.models.model_execution_observations import (
    FallbackObservation,
    FoodDecisionObservation,
    ModelExecutionEventStatus,
)
from infrastructure.models.model_execution_ports import (
    ModelExecutionAgentPorts,
)
from infrastructure.models.model_reference import parse_model_reference

logger = logging.getLogger("infrastructure.models.model_execution_agent")
MainFoodLoader = Callable[[str], MainFoodSelection]
_ADOPTION_MODEL_TIMEOUT_SECONDS = 20.0


class _UnavailableToolPort:
    """Semantic no-op used when an isolated model execution has no tool scope."""

    def available_tool_keys(self) -> tuple[ToolKey, ...]:
        return ()

    def available_tool_definitions(self) -> tuple[ToolDefinition, ...]:
        return ()

    def execute(self, request: ToolRequest) -> ToolResult:
        message = "该工具在当前模型执行作用域未注入。"
        return ToolResult(
            tool_key=request.tool_key,
            ok=False,
            content=message,
            error=ErrorInfo(code="tool_unavailable", message=message),
        )


class ModelExecutionAgent:
    """外包算力工厂底层 Agent - 拥有三轨自演化技能与原生多模态 Payload 组装能力"""

    def __init__(
        self,
        config: ModelExecutionConfig,
        *,
        ports: ModelExecutionAgentPorts,
        live_reload: bool = False,
        main_food_loader: MainFoodLoader | None = None,
        food_catalog_repository: FoodPort | None = None,
        tool_port: ToolPort | None = None,
    ):
        self.config = config
        self._ports = ports
        self._live_reload = live_reload
        self._main_food_loader = main_food_loader
        self.food_catalog_repository = food_catalog_repository
        self.tool_port: ToolPort = (
            tool_port if tool_port is not None else _UnavailableToolPort()
        )
        self._config_mtimes_ns = self._config_mtimes()
        self._mount_execution_dependencies()

    def _mount_execution_dependencies(self) -> None:
        self._observer = self._ports.observer

    def _config_mtimes(self) -> tuple[int | None, ...]:
        mtimes: list[int | None] = []
        for path in self._ports.config_paths():
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
        self.config = self._ports.model_execution_config_loader()
        self._config_mtimes_ns = current_mtimes
        self._mount_execution_dependencies()

    def ask(
        self,
        prompt: str,
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_tools: List[str] | None = None,
    ) -> str:
        """兼容文本接口；内部只转换成粮食请求，不再直接选择模型。"""
        tools = (
            tuple(allowed_tools)
            if allowed_tools is not None
            else ("web_search", "local_file")
        )
        return self.run_with_food(
            prompt=prompt,
            food_key=None,
            energy=energy,
            task_complexity=task_complexity,
            allowed_tools=list(tools),
        ).text

    def ask_with_food(
        self,
        prompt: str,
        food_key: str | None,
        elfie_id: str | None = None,
        scene: str = "chat",
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_tools: List[str] | None = None,
        semantic_role: str = "primary",
        images: List[str] | None = None,
        audio: str | None = None,
    ) -> str:
        """粮食语义文本接口。"""
        return self.run_with_food(
            prompt=prompt,
            food_key=food_key,
            elfie_id=elfie_id,
            scene=scene,
            energy=energy,
            task_complexity=task_complexity,
            allowed_tools=allowed_tools,
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
        scene: str = "chat",
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_tools: List[str] | None = None,
        semantic_role: str = "primary",
        images: List[str] | None = None,
        audio: str | None = None,
    ) -> ModelExecutionResult:
        """返回完整执行结果，调用者仍只提交粮食语义和任务上下文。"""
        self._reload_config_if_changed()
        configured_tools = self._ports.effective_tool_keys(
            self.config.runtime_policy,
            tuple(allowed_tools or ()),
        )
        available_tools = set(self.tool_port.available_tool_keys())
        tools = tuple(tool for tool in configured_tools if tool in available_tools)
        request = ModelExecutionRequest(
            prompt=prompt,
            energy=energy,
            task_complexity=task_complexity,
            allowed_tools=tools,
            elfie_id=elfie_id,
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

    def think(self, request: ModelExecutionRequest) -> ModelExecutionResult:
        self._reload_config_if_changed()
        return self._think_with_food(request)

    def structured_capabilities(
        self,
        food_key: str | None = None,
        food_unavailable: bool = False,
    ) -> StructuredModelExecutionCapabilities:
        """Describe the primary role of the selected food package."""
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(
            catalog,
            food_key,
            unavailable=food_unavailable,
            is_usable=self._package_usable,
        )
        assignment = catalog.packages[selected_food].primary
        if assignment is None:
            raise NoAvailableFoodError("no_available_food")
        provider = self._provider_for_model(assignment.model)
        provider_config = self.config.providers.get(provider, {})
        native = provider == "openai" or provider_config.get("catalog_id") in {
            "openai_api",
            "openai_chatgpt",
        }
        supports_tools = self._supports_native_tool_calling(assignment.model, provider)
        api_mode = str(provider_config.get("api_mode") or "")
        is_ollama = (
            provider == "ollama"
            or provider.startswith("ollama_")
            or api_mode == "ollama"
        )
        return StructuredModelExecutionCapabilities(
            provider=provider,
            model_key=assignment.model,
            supports_json_schema=native,
            supports_tool_calling=supports_tools,
            supports_json_mode=native or is_ollama or api_mode == "chat_completions",
            supports_plain_text=True,
            max_output_tokens=4096,
        )

    def adoption_capabilities(self) -> StructuredModelExecutionCapabilities:
        """Read the persisted readiness of the remote common Food only."""
        self._reload_config_if_changed()
        package = self._adoption_package()
        assert package.primary is not None
        provider = self._provider_for_model(package.primary.model)
        provider_config = self.config.providers.get(provider, {})
        native = provider == "openai" or provider_config.get("catalog_id") in {
            "openai_api",
            "openai_chatgpt",
        }
        supports_tools = self._supports_native_tool_calling(
            package.primary.model, provider
        )
        api_mode = str(provider_config.get("api_mode") or "")
        return StructuredModelExecutionCapabilities(
            provider=provider,
            model_key=package.primary.model,
            supports_json_schema=native,
            supports_tool_calling=supports_tools,
            supports_json_mode=native or api_mode == "chat_completions",
            supports_plain_text=True,
            max_output_tokens=4096,
        )

    def generate_adoption_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        """Execute Adoption identity prose on the qualified remote common Food."""
        self._reload_config_if_changed()
        package = self._adoption_package()
        assert package.primary is not None
        if request.model_key and request.model_key != package.primary.model:
            raise NoAvailableFoodError("adoption_model_changed")
        messages = (
            [message.model_dump(mode="python") for message in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )
        provider = self._provider_for_model(package.primary.model)
        started = perf_counter()
        executor = self._food_executor(
            provider_options=self._structured_request_options(
                request, request.selected_mode
            ),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            thinking=request.reasoning_mode == "long",
            timeout_seconds=(
                request.timeout_seconds
                if request.timeout_seconds is not None
                else _ADOPTION_MODEL_TIMEOUT_SECONDS
            ),
        )
        try:
            execution = executor.execute(
                package,
                self._structured_messages(request, request.selected_mode, messages),
                semantic_role="primary",
                allowed_tools=(),
                allow_fallback=False,
                scope_id=request.scope_id,
            )
        except Exception as error:
            raise NoAvailableFoodError(
                f"no_available_adoption_model: {error}"
            ) from error
        return StructuredModelExecutionResult(
            text=execution.text,
            selected_mode=request.selected_mode,
            provider=provider,
            model_key=execution.model,
            latency_ms=(perf_counter() - started) * 1000.0,
            tool_calls=execution.tool_calls,
            skill_calls=execution.skill_calls,
        )

    def generate_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        """Execute exactly one structured generation using the selected mode."""
        self._reload_config_if_changed()
        catalog = self._load_food_catalog()
        selected_food = self._select_food_key(
            catalog,
            request.food_key,
            unavailable=request.food_unavailable,
            is_usable=self._package_usable,
        )
        attempts = [(selected_food, request.selected_mode)]
        if request.allow_fallback and selected_food != FOOD_EMERGENCY_ID:
            emergency = catalog.packages.get(FOOD_EMERGENCY_ID)
            if emergency and self._package_usable(emergency):
                fallback_mode = (
                    StructuredGenerationMode.PLAIN_TEXT
                    if request.selected_mode is StructuredGenerationMode.PLAIN_TEXT
                    else StructuredGenerationMode.JSON_TEXT
                )
                attempts.append((FOOD_EMERGENCY_ID, fallback_mode))
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
            try:
                execution = self._execute_structured_assignment(
                    assignment=assignment,
                    request=request,
                    selected_mode=selected_mode,
                    messages=self._structured_messages(
                        request, selected_mode, messages
                    ),
                )
            except Exception as exc:
                failures.append(f"{attempt_food}: {exc}")
                continue
            return StructuredModelExecutionResult(
                text=execution.text,
                selected_mode=selected_mode,
                provider=provider,
                model_key=execution.model,
                latency_ms=(perf_counter() - started) * 1000.0,
                tool_calls=execution.tool_calls,
                skill_calls=execution.skill_calls,
            )
        raise NoAvailableFoodError("no_available_food: " + " | ".join(failures))

    @staticmethod
    def _structured_messages(
        request: StructuredModelExecutionRequest,
        selected_mode: StructuredGenerationMode,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Add a host-owned schema instruction when the provider lacks native schema."""
        copied = [dict(message) for message in messages]
        if (
            selected_mode is not StructuredGenerationMode.JSON_TEXT
            or request.brain_owned_system_prompt
        ):
            return copied
        instruction = (
            "Return only one JSON value. Do not use Markdown or explanatory text. "
            f"The value must validate against this {request.response_schema_name} "
            "JSON Schema:\n"
            + json.dumps(
                request.response_schema, ensure_ascii=False, separators=(",", ":")
            )
        )
        if copied and copied[0].get("role") == "system":
            copied[0]["content"] = f"{copied[0].get('content', '')}\n\n{instruction}"
        else:
            copied.insert(0, {"role": "system", "content": instruction})
        return copied

    @staticmethod
    def _provider_for_model(model_key: str) -> str:
        return parse_model_reference(model_key).connection_id

    @staticmethod
    def _model_name(model_key: str) -> str:
        return parse_model_reference(model_key).model_id

    @staticmethod
    def _structured_request_options(
        request: StructuredModelExecutionRequest,
        selected_mode: StructuredGenerationMode,
    ) -> Dict[str, Any]:
        if selected_mode is StructuredGenerationMode.PLAIN_TEXT:
            return {}
        options: Dict[str, Any] = {}
        tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": dict(definition.input_schema),
                },
            }
            for definition in request.tool_definitions
        ]
        if request.reasoning_mode == "fast" and request.model_key:
            profile = resolve_model_capability_profile(request.model_key)
            if profile and profile.canonical_name.startswith("GLM-"):
                # GLM-5 enables thinking by default. Structured fast paths need
                # the final JSON payload rather than its visible reasoning trace.
                options["thinking"] = {"type": "disabled"}
        if selected_mode is StructuredGenerationMode.JSON_SCHEMA:
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema_name,
                    "schema": dict(request.response_schema),
                    "strict": True,
                },
            }
            if tool_definitions:
                options["tool_definitions"] = tool_definitions
                options["tool_choice"] = "auto"
            return options
        if selected_mode is StructuredGenerationMode.TOOL_CALL:
            tool_definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": request.response_schema_name,
                        "description": "Return the final structured DecisionPlan.",
                        "parameters": dict(request.response_schema),
                    },
                }
            )
            options["tool_definitions"] = tool_definitions
            options["tool_choice"] = "auto"
            return options
        # Ollama's JSON_TEXT mode still needs an explicit JSON constraint;
        # without it small local models commonly echo the prompt or markdown.
        provider = request.provider or ""
        if provider == "ollama" or provider.startswith("ollama_"):
            options["format"] = "json"
        return options

    def _execute_structured_assignment(
        self,
        *,
        assignment: Any,
        request: StructuredModelExecutionRequest,
        selected_mode: StructuredGenerationMode,
        messages: list[dict[str, Any]],
    ) -> FoodExecutionResult:
        """Call one Provider once and preserve native Tool calls for Brain."""
        reference = parse_model_reference(assignment.model)
        provider = reference.connection_id
        options = self._structured_request_options(request, selected_mode)
        with self._model_call_scope(
            provider,
            reference.model_id,
            food_id=request.food_key or "structured",
            semantic_role="primary",
            route_stage="primary",
            scope_id=request.scope_id,
        ):
            call_args = (
                provider,
                reference.model_id,
                messages,
                request.temperature,
                request.max_tokens,
                options,
                request.reasoning_mode == "long",
            )
            raw = (
                self._call_food_llm_api(*call_args)
                if request.timeout_seconds is None
                else self._call_food_llm_api(
                    *call_args,
                    timeout_seconds=request.timeout_seconds,
                )
            )
        result = raw if isinstance(raw, LLMCallResult) else LLMCallResult(raw, {}, {})
        tool_calls = tuple(
            call
            for call in result.tool_calls
            if call.tool_key != request.response_schema_name
        )
        final_calls = tuple(
            call
            for call in result.tool_calls
            if call.tool_key == request.response_schema_name
        )
        skill_calls: tuple[SkillLoadCall, ...] = result.skill_calls
        text = result.text
        if not text and final_calls:
            text = json.dumps(
                dict(final_calls[0].arguments),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        return FoodExecutionResult(
            text=text,
            model=assignment.model,
            execution_stage="primary",
            technical_fallback_used=False,
            tool_calls=tool_calls,
            skill_calls=skill_calls,
        )

    def _supports_native_tool_calling(self, model_key: str, provider: str) -> bool:
        """Require an endpoint declaration or verified evidence before exposure."""
        provider_config = self.config.providers.get(provider, {})
        if provider_config.get("supports_tools") is True:
            return True
        model_id = self._model_name(model_key)
        raw_models = provider_config.get("models", ())
        if isinstance(raw_models, list):
            for raw_model in raw_models:
                if not isinstance(raw_model, dict):
                    continue
                if str(raw_model.get("id") or raw_model.get("model_id")) != model_id:
                    continue
                if raw_model.get("supports_tools") is True:
                    return True
        ports = getattr(self, "_ports", None)
        evidence_source = getattr(ports, "model_evidence_source", None)
        evidence = evidence_source().get(model_key) if evidence_source else None
        return bool(
            evidence
            and evidence.fresh
            and (
                evidence.tool_test_passed
                or evidence.capability_states.get("tools") == "supported"
            )
        )

    @staticmethod
    def _model_call_scope(
        provider: str,
        model: str,
        *,
        food_id: str,
        semantic_role: str,
        route_stage: str,
        scope_id: str | None,
    ):
        from infrastructure.models.model_execution_observations import (
            ModelCallContext,
            scoped_model_call_context,
        )

        return scoped_model_call_context(
            ModelCallContext(
                connection_id=provider,
                endpoint_model_id=model,
                food_id=food_id,
                semantic_role=semantic_role,
                route_stage=route_stage,
                workload_kind="production",
                scope_id=scope_id,
            )
        )

    def _think_with_food(self, request: ModelExecutionRequest) -> ModelExecutionResult:
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
            tool_port=self.tool_port,
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
                scope_id=request.elfie_id,
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
                scope_id=request.elfie_id,
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
        observer = self._observer
        if fallback_used or (
            selected_food == FOOD_EMERGENCY_ID and requested_food != FOOD_EMERGENCY_ID
        ):
            requested_package = catalog.packages.get(requested_food)
            previous_model = (
                failed_attempts[-1].get("model", "")
                if failed_attempts
                else (
                    requested_package.primary.model
                    if requested_package is not None
                    and requested_package.primary is not None
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
                status=ModelExecutionEventStatus.OK,
                requested_food_id=requested_food,
                semantic_role=request.semantic_role,
                model=execution.model,
                reason=selection_reason,
            )
        )
        return ModelExecutionResult(
            text=execution.text,
            mode="local" if provider == "ollama" else "remote",
            model_key=execution.model,
            decision=cast(
                dict[str, JsonValue],
                {
                    "food": {
                        "requested": requested_food,
                        "actual": selected_food,
                        "reason": selection_reason,
                    },
                    "scene": request.scene,
                    "attempts": [*failed_attempts, *execution.attempts],
                },
            ),
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
        request: ModelExecutionRequest,
        allowed_tools: tuple[str, ...],
        scope_id: str | None,
    ) -> FoodExecutionResult:
        return executor.execute(
            package,
            messages,
            allowed_tools=allowed_tools,
            max_loops=3,
            semantic_role=(request.semantic_role),
            images=request.images,
            audio=request.audio,
            scope_id=scope_id,
        )

    @staticmethod
    def _select_food_key(
        catalog: FoodCatalog,
        requested_food: str | None,
        *,
        unavailable: bool = False,
        is_usable: Callable[[FoodPackage], bool] | None = None,
    ) -> str:
        return resolve_main_food(
            catalog,
            MainFoodSelection(requested_food, unavailable=unavailable),
            is_usable=is_usable
            or (lambda package: package.enabled and not package.archived),
        ).food_id

    def _main_food_selection(self, request: ModelExecutionRequest) -> MainFoodSelection:
        if request.elfie_id and self._main_food_loader is not None:
            return self._main_food_loader(request.elfie_id)
        return MainFoodSelection(request.food_key)

    def _package_usable(self, package: FoodPackage) -> bool:
        evidence = self._ports.model_evidence_source()
        if not is_food_executable(
            package,
            is_model_available=lambda reference: bool(
                evidence.get(reference) and evidence[reference].fresh
            ),
        ):
            return False
        try:
            assert package.primary is not None
            provider = ModelExecutionAgent._provider_for_model(package.primary.model)
            return provider in self.config.providers
        except Exception:
            return False

    def _adoption_package(self) -> FoodPackage:
        catalog = self._load_food_catalog()
        package = catalog.packages.get(catalog.global_default_food_id)
        if package is None or not self._adoption_package_usable(package):
            raise NoAvailableFoodError("no_available_adoption_model")
        return package

    def _adoption_package_usable(self, package: FoodPackage) -> bool:
        if not package.enabled or package.archived or package.primary is None:
            return False
        evidence = self._ports.model_evidence_source().get(package.primary.model)
        if evidence is None or evidence.local or not evidence.fresh:
            return False
        try:
            provider = self._provider_for_model(package.primary.model)
            provider_config = self.config.providers.get(provider)
            return bool(
                provider_config is not None
                and provider_config.get("status", "active") != "inactive"
            )
        except Exception:
            return False

    def _food_executor(
        self,
        *,
        provider_options: Dict[str, Any] | None = None,
        temperature: float,
        max_tokens: int,
        thinking: bool = False,
        timeout_seconds: float | None = None,
    ) -> FoodExecutor:
        def caller(
            provider: str,
            model: str,
            messages: list[dict[str, Any]],
            _temperature: float,
            _max_tokens: int,
            options: dict[str, Any],
        ) -> LLMCallResult:
            call_args = (
                provider,
                model,
                messages,
                temperature,
                max_tokens,
                {**options, **(provider_options or {})},
                thinking,
            )
            if timeout_seconds is None:
                return self._call_food_llm_api(*call_args)
            return self._call_food_llm_api(*call_args, timeout_seconds)

        return FoodExecutor(
            config=self.config,
            tool_port=self.tool_port,
            model_caller=caller,
        )

    def _load_food_catalog(self) -> FoodCatalog:
        if self.food_catalog_repository is None:
            raise RuntimeError("模型执行未注入粮食数据库仓储")
        catalog = self.food_catalog_repository.load()
        if not catalog.packages:
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
        thinking: bool = False,
        timeout_seconds: float | None = None,
    ) -> LLMCallResult:
        """Execute one provider request and retain any native Tool calls."""
        return call_llm_api_result(
            self.config,
            provider,
            model_name,
            messages,
            temperature,
            max_tokens,
            thinking=thinking,
            request_options=request_options,
            timeout_seconds=timeout_seconds,
        )
