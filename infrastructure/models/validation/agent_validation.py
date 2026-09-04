"""Validate one model's native Tool-call protocol against the real ToolPort."""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Union

from pydantic import JsonValue

from elfie.brain.reasoning.tool_port import (
    ToolCall,
    ToolDefinition,
    ToolOperation,
    ToolPort,
    ToolRequest,
)
from elfie.message_types import ElfieId
from infrastructure.models.inference.llm_api import LLMCallResult, call_llm_api_result
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)

AgentModelCaller = Callable[
    [str, str, list[dict[str, JsonValue]], float, int, dict[str, JsonValue]],
    Union[str, LLMCallResult],
]
AgentToolPortFactory = Callable[[ModelExecutionConfig, Path, str], ToolPort]


class ModelAgentValidationRunner:
    """Run a bounded, provider-neutral native Tool integration probe."""

    def __init__(
        self,
        config: ModelExecutionConfig,
        *,
        model_caller: AgentModelCaller | None = None,
        tool_port_factory: AgentToolPortFactory,
    ) -> None:
        self.config = config
        self.model_caller = model_caller or self._call_model
        self._tool_port_factory = tool_port_factory
        # Each default (real-provider) model call leaves a bounded, secret-free
        # request/response record here so a native Tool probe is inspectable.
        # Custom callers remain free to provide their own test instrumentation.
        self.traces: list[dict[str, JsonValue]] = []

    def verify(
        self,
        provider: str,
        model: str,
        tools: Sequence[str] = ("local_file",),
    ) -> ValidationSuite:
        return ValidationSuite(
            name=f"agent:{provider}/{model}",
            results=tuple(
                self.verify_tool(provider, model, tool_name) for tool_name in tools
            ),
        )

    def verify_tool(self, provider: str, model: str, tool_name: str) -> CheckResult:
        check_id = f"agent.{provider}.{model}.{tool_name}"
        if tool_name not in {"local_file", "web_search"}:
            return CheckResult(
                check_id=check_id,
                status=CheckStatus.SKIPPED,
                message="Model integration scenario not defined for this tool",
                provider=provider,
                model=model,
            )

        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="elfie-agent-check-") as temp_dir:
                root = Path(temp_dir)
                files_root = root / "files"
                files_root.mkdir()
                (files_root / "probe.txt").write_text(
                    "ELFIE_LOCAL_FILE_OK", encoding="utf-8"
                )
                policy = deepcopy(getattr(self.config, "runtime_policy", {}))
                configured_tools = policy.setdefault("tools", {})
                configured_tools.setdefault(tool_name, {})["enabled"] = True
                validation_config = replace(self.config, runtime_policy=policy)
                tool_port = self._tool_port_factory(
                    validation_config, files_root, tool_name
                )
                definition = next(
                    (
                        item
                        for item in tool_port.available_tool_definitions()
                        if item.name == tool_name
                    ),
                    None,
                )
                if definition is None:
                    return self._result(
                        check_id,
                        CheckStatus.FAILED,
                        "ToolPort did not expose the requested native definition",
                        started,
                        provider,
                        model,
                        {"tool_called": False},
                    )

                messages: list[dict[str, JsonValue]] = [
                    {"role": "user", "content": _tool_probe_prompt(tool_name)}
                ]
                tool_definitions: list[JsonValue] = [_provider_definition(definition)]
                request_options: dict[str, JsonValue] = {
                    "tool_definitions": tool_definitions,
                    "tool_choice": "auto",
                }
                first = self.model_caller(
                    provider,
                    model,
                    messages,
                    0.0,
                    256,
                    request_options,
                )
                if not isinstance(first, LLMCallResult):
                    return self._result(
                        check_id,
                        CheckStatus.FAILED,
                        "模型返回纯文本，未提供原生 Tool call；文本标记不再受支持",
                        started,
                        provider,
                        model,
                        {"tool_called": False, "native_protocol": False},
                    )

                calls = tuple(
                    call for call in first.tool_calls if call.tool_key == tool_name
                )
                if not calls:
                    return self._result(
                        check_id,
                        CheckStatus.FAILED,
                        "模型未返回请求 Tool 的原生调用",
                        started,
                        provider,
                        model,
                        {
                            "tool_called": False,
                            "native_protocol": True,
                            "returned_tool_calls": len(first.tool_calls),
                        },
                    )

                executed: list[tuple[ToolCall, str]] = []
                for call in calls:
                    result = tool_port.execute(_tool_request(call, tool_name))
                    if not result.ok:
                        return self._result(
                            check_id,
                            CheckStatus.FAILED,
                            f"ToolPort 执行失败: {result.content}",
                            started,
                            provider,
                            model,
                            {
                                "tool_called": True,
                                "observation_received": False,
                            },
                        )
                    executed.append((call, result.content))
                provider_config = self.config.providers.get(provider, {})
                api_mode = str(provider_config.get("api_mode") or "chat_completions")
                _append_tool_exchange(messages, first, executed, api_mode)
                second = self.model_caller(
                    provider,
                    model,
                    messages,
                    0.0,
                    256,
                    request_options,
                )
                final_text = (
                    second.text if isinstance(second, LLMCallResult) else str(second)
                )
                passed = (
                    isinstance(second, LLMCallResult)
                    and bool(final_text.strip())
                    and not second.tool_calls
                )
                return self._result(
                    check_id,
                    CheckStatus.PASSED if passed else CheckStatus.FAILED,
                    (
                        "Model Agent native Tool invocation passed"
                        if passed
                        else "Tool observation was returned but model did not finish with a final answer"
                    ),
                    started,
                    provider,
                    model,
                    {
                        "tool_called": True,
                        "observation_received": True,
                        "final_answer": bool(final_text.strip()),
                        "native_protocol": True,
                        "model_calls": 2,
                    },
                )
        except Exception as exc:
            return self._result(
                check_id,
                CheckStatus.FAILED,
                str(exc),
                started,
                provider,
                model,
                {"error_type": type(exc).__name__},
            )

    @staticmethod
    def _result(
        check_id: str,
        status: CheckStatus,
        message: str,
        started: float,
        provider: str,
        model: str,
        details: Mapping[str, JsonValue],
    ) -> CheckResult:
        return CheckResult(
            check_id=check_id,
            status=status,
            message=message,
            duration_ms=(time.perf_counter() - started) * 1000,
            provider=provider,
            model=model,
            details=dict(details),
        )

    def _call_model(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, JsonValue]],
        temperature: float,
        max_tokens: int,
        request_options: dict[str, JsonValue],
    ) -> LLMCallResult:
        capture: dict[str, JsonValue] = {}
        try:
            result = call_llm_api_result(
                self.config,
                provider,
                model,
                messages,
                temperature,
                max_tokens,
                request_options=request_options,
                response_capture=capture,
            )
        except Exception as error:
            capture["error"] = {"type": type(error).__name__}
            self.traces.append({"provider": provider, "model": model, **capture})
            raise
        self.traces.append({"provider": provider, "model": model, **capture})
        return result


def _provider_definition(definition: ToolDefinition) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "function": {
            "name": definition.name,
            "description": definition.description,
            "parameters": dict(definition.input_schema),
        },
    }


def _tool_request(call: ToolCall, tool_name: str) -> ToolRequest:
    arguments = dict(call.arguments)
    if tool_name == "web_search":
        return ToolRequest(
            tool_key=tool_name,
            operation="search",
            query=str(arguments.get("query") or ""),
            max_results=_json_int(arguments.get("max_results", 3), 3),
        )
    return ToolRequest(
        scope_id=ElfieId("validation"),
        tool_key=tool_name,
        operation=_tool_operation(arguments.get("operation"), "read"),
        resource_id=str(arguments.get("resource_id") or ""),
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


def _append_tool_exchange(
    messages: list[dict[str, JsonValue]],
    response: LLMCallResult,
    executed_tools: list[tuple[ToolCall, str]],
    api_mode: str,
) -> None:
    if api_mode == "anthropic_messages":
        assistant_content: list[JsonValue] = []
        if response.text:
            assistant_content.append({"type": "text", "text": response.text})
        assistant_content.extend(
            {
                "type": "tool_use",
                "id": call.call_id,
                "name": call.tool_key,
                "input": dict(call.arguments),
            }
            for call, _content in executed_tools
        )
        tool_results: list[JsonValue] = [
            {
                "type": "tool_result",
                "tool_use_id": call.call_id,
                "content": content,
            }
            for call, content in executed_tools
        ]
        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
            }
        )
        messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
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


def _tool_probe_prompt(tool_name: str) -> str:
    if tool_name == "local_file":
        return "请必须读取本地文件 probe.txt，并根据文件内容回答。"
    return "请必须使用联网搜索工具搜索 ElfieNest，并根据搜索结果回答。"
