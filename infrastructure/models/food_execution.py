"""Execute one Elfie Food package role through model and tool Adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import JsonValue

from elfie.brain.reasoning.food_port import (
    FoodAssignment,
    FoodPackage,
)
from elfie.brain.reasoning.skill_port import SkillLoadCall
from elfie.brain.reasoning.tool_port import (
    ToolCall,
    ToolOperation,
    ToolPort,
    ToolRequest,
)
from elfie.message_types import ElfieId
from infrastructure.models.inference.llm_api import LLMCallResult
from infrastructure.models.inference.multimodal import assemble_multimodal_payload
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_observations import (
    ModelCallContext,
    scoped_model_call_context,
)
from infrastructure.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)

_TOOL_OPERATIONS: dict[str, ToolOperation] = {
    "search": "search",
    "read": "read",
    "list": "list",
}


def _json_int(value: JsonValue, default: int) -> int:
    if isinstance(value, (str, int, float)):
        return int(value)
    return default


def _tool_operation(value: JsonValue, default: ToolOperation) -> ToolOperation:
    if isinstance(value, str):
        return _TOOL_OPERATIONS.get(value, default)
    return default


@dataclass(frozen=True)
class FoodExecutionResult:
    text: str
    model: str
    execution_stage: str
    technical_fallback_used: bool
    attempts: tuple[dict[str, str], ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    skill_calls: tuple[SkillLoadCall, ...] = ()


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
            [str, str, list[dict[str, Any]], float, int, dict[str, Any]],
            str | LLMCallResult,
        ],
    ) -> None:
        self.config = config
        self.tool_port = tool_port
        self.model_caller = model_caller

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
        tool_options = self._tool_options(effective_tools)
        api_mode = str(provider_config.get("api_mode") or "chat_completions")

        def invoke(loop_messages: list[dict[str, Any]]) -> str | LLMCallResult:
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
                    tool_options,
                )

        for _loop_index in range(max_loops):
            raw = invoke(messages)
            if not isinstance(raw, LLMCallResult):
                return str(raw)
            if not raw.tool_calls:
                return raw.text
            if not effective_tools:
                return raw.text
            executed_tools: list[tuple[ToolCall, str]] = []
            for call in raw.tool_calls:
                if call.tool_key not in effective_tools:
                    raise FoodExecutionError(f"模型请求了未授权 Tool: {call.tool_key}")
                request = self._tool_request(call, scope_id)
                result = self.tool_port.execute(request)
                if not result.ok:
                    raise FoodExecutionError(
                        f"Tool {call.tool_key} 执行失败: {result.content}"
                    )
                executed_tools.append((call, result.content))
            self._append_tool_exchange(messages, raw, executed_tools, api_mode)
        raise TimeoutError("❌ 原生 Tool 调用循环超过本次请求的迭代上限。")

    def _tool_options(self, effective_tools: tuple[str, ...]) -> dict[str, Any]:
        definition_loader = getattr(self.tool_port, "available_tool_definitions", None)
        definitions = tuple(
            definition
            for definition in (definition_loader() if definition_loader else ())
            if definition.name in effective_tools
        )
        if not definitions:
            return {}
        return {
            "tool_definitions": [
                {
                    "type": "function",
                    "function": {
                        "name": definition.name,
                        "description": definition.description,
                        "parameters": dict(definition.input_schema),
                    },
                }
                for definition in definitions
            ],
            "tool_choice": "auto",
        }

    @staticmethod
    def _tool_request(call: ToolCall, scope_id: str | None) -> ToolRequest:
        arguments = dict(call.arguments)
        if call.tool_key == "web_search":
            return ToolRequest(
                tool_key=call.tool_key,
                operation="search",
                query=str(arguments.get("query") or ""),
                max_results=_json_int(arguments.get("max_results", 3), 3),
            )
        return ToolRequest(
            scope_id=ElfieId(scope_id) if scope_id is not None else None,
            tool_key=call.tool_key,
            operation=_tool_operation(arguments.get("operation"), "read"),
            resource_id=str(arguments.get("resource_id") or ""),
        )

    @staticmethod
    def _append_tool_exchange(
        messages: list[dict[str, Any]],
        response: LLMCallResult,
        executed_tools: list[tuple[ToolCall, str]],
        api_mode: str,
    ) -> None:
        """Append the provider-native assistant/tool exchange for the next call."""
        if api_mode == "anthropic_messages":
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        *(
                            [{"type": "text", "text": response.text}]
                            if response.text
                            else []
                        ),
                        *[
                            {
                                "type": "tool_use",
                                "id": call.call_id,
                                "name": call.tool_key,
                                "input": dict(call.arguments),
                            }
                            for call, _content in executed_tools
                        ],
                    ],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call.call_id,
                            "content": content,
                        }
                        for call, content in executed_tools
                    ],
                }
            )
            return
        if api_mode == "codex_responses":
            messages.append(
                {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": [
                        {
                            "id": call.call_id,
                            "type": "function",
                            "function": {
                                "name": call.tool_key,
                                "arguments": json.dumps(
                                    dict(call.arguments), ensure_ascii=False
                                ),
                            },
                        }
                        for call, _content in executed_tools
                    ],
                }
            )
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": content,
                }
                for call, content in executed_tools
            )
            return
        messages.append(
            {
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.tool_key,
                            "arguments": json.dumps(
                                dict(call.arguments), ensure_ascii=False
                            ),
                        },
                    }
                    for call, _content in executed_tools
                ],
            }
        )
        messages.extend(
            {
                "role": "tool",
                "tool_call_id": call.call_id,
                "content": content,
            }
            for call, content in executed_tools
        )
