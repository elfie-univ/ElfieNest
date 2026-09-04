from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Callable, Protocol

from pydantic import JsonValue

from elfie.brain.reasoning.tool_port import ToolRequest
from infrastructure.tools.execution.config import SAFE_TOOL_KEYS
from infrastructure.tools.execution.observation import (
    ToolCallObservation,
    ToolMetadataValue,
    ToolObservationPort,
)

logger = logging.getLogger("infrastructure.tools.executor")

ToolData = dict[str, ToolMetadataValue]


class SearchPlugin(Protocol):
    def search(self, query: str) -> str: ...


class PermissionManager(Protocol):
    def verify_action(
        self, action: str, file_path: str | None = None, token: str | None = None
    ) -> bool: ...


class FileAccessPlugin(Protocol):
    def read_text(self, relative_path: str) -> str: ...

    def list_files(self, relative_path: str = ".") -> list[str]: ...


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    ok: bool
    content: str
    metadata: Mapping[str, ToolMetadataValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecutionContext:
    allowed_tool_keys: tuple[str, ...]
    search_plugin: SearchPlugin
    permission_manager: PermissionManager
    observation_port: ToolObservationPort
    owner_token: str | None = None
    file_access_plugin: FileAccessPlugin | None = None
    max_result_bytes: int = 16000
    max_total_result_bytes: int = 48000
    max_tool_calls: int = 3
    runtime_enabled_tools: tuple[str, ...] = SAFE_TOOL_KEYS
    tool_configs: Mapping[str, Mapping[str, JsonValue]] = field(default_factory=dict)


class ToolExecutor:
    def __init__(self, context: ToolExecutionContext):
        self.context = context
        self._tool_calls = 0
        self._retained_result_bytes = 0

    def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one validated semantic request without text markers."""
        if not self._can_use(request.tool_key):
            return self._record_tool_result(
                ToolResult(
                    tool_name=request.tool_key,
                    ok=False,
                    content="工具未被当前作用域授权或启用。",
                    metadata={"error_type": "tool_denied"},
                )
            )
        return self._record_tool_result(
            self._execute_with_guard(
                request.tool_key,
                lambda: self._execute_request(request),
            )
        )

    def _execute_request(self, request: ToolRequest) -> ToolResult:
        if request.tool_key == "web_search":
            return self._execute_search(request)
        if request.tool_key == "local_file" and request.operation == "read":
            return self._execute_read_file(request)
        if request.tool_key == "local_file" and request.operation == "list":
            return self._execute_list_files(request)
        return ToolResult(
            tool_name=request.tool_key,
            ok=False,
            content="工具操作不受支持。",
            metadata={"error_type": "operation_unsupported"},
        )

    def _execute_read_file(self, request: ToolRequest) -> ToolResult:
        path = request.resource_id
        assert path is not None
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult(
                request.tool_key,
                False,
                "本地文件工具未配置",
                {"error_type": "tool_unavailable"},
            )
        self.context.permission_manager.verify_action(
            "READ",
            file_path="runtime_workspace",
        )
        content = plugin.read_text(path)
        bounded, envelope_truncated = _bounded(
            content,
            self._result_budget("local_file"),
        )
        source_bytes = int(
            getattr(plugin, "last_read_bytes", len(content.encode("utf-8")))
        )
        source_truncated = bool(getattr(plugin, "last_read_truncated", False))
        return ToolResult(
            tool_name=request.tool_key,
            ok=True,
            content=f"【本地文件内容】\n{bounded}",
            metadata={
                "truncated": source_truncated or envelope_truncated,
                "bytes": source_bytes,
                "retained_bytes": len(bounded.encode("utf-8")),
            },
        )

    def _execute_list_files(self, request: ToolRequest) -> ToolResult:
        path = request.resource_id or "."
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult(
                request.tool_key,
                False,
                "本地文件工具未配置",
                {"error_type": "tool_unavailable"},
            )
        self.context.permission_manager.verify_action(
            "READ",
            file_path="runtime_workspace",
        )
        files = plugin.list_files(path)
        payload, envelope_truncated = _bounded(
            "\n".join(files), self._result_budget("local_file")
        )
        source_items = int(getattr(plugin, "last_list_items", len(files)))
        source_truncated = bool(getattr(plugin, "last_list_truncated", False))
        return ToolResult(
            tool_name=request.tool_key,
            ok=True,
            content="【本地目录文件】\n" + payload,
            metadata={
                "truncated": source_truncated or envelope_truncated,
                "items": source_items,
                "retained_items": len(payload.splitlines()) if payload else 0,
            },
        )

    def _can_use(self, tool_key: str) -> bool:
        return (
            tool_key in SAFE_TOOL_KEYS
            and tool_key in self.context.allowed_tool_keys
            and tool_key in self.context.runtime_enabled_tools
        )

    def _execute_search(self, request: ToolRequest) -> ToolResult:
        query = request.query
        assert query is not None
        self.context.permission_manager.verify_action(
            "WEB_SEARCH",
            file_path="search_query",
        )
        search_result = self.context.search_plugin.search(query)
        bounded, truncated = _bounded(search_result, self._result_budget("web_search"))
        logger.info("已成功回调联网检索数据。")
        return ToolResult(
            tool_name="web_search",
            ok=True,
            content="【联网搜索反馈】\n" + bounded,
            metadata={
                "truncated": truncated,
                "bytes": len(search_result.encode("utf-8")),
                "retained_bytes": len(bounded.encode("utf-8")),
            },
        )

    def _execute_with_guard(
        self,
        tool_key: str,
        execute: Callable[[], ToolResult],
    ) -> ToolResult:
        if self._tool_calls >= self.context.max_tool_calls:
            return ToolResult(
                tool_name=tool_key,
                ok=False,
                content="工具调用次数已达到本次请求上限。",
                metadata={
                    "limit": "tool_calls",
                    "max_tool_calls": self.context.max_tool_calls,
                },
            )
        if self._remaining_result_bytes() <= 0:
            return ToolResult(
                tool_name=tool_key,
                ok=False,
                content="工具结果字节预算已耗尽。",
                metadata={
                    "limit": "total_result_bytes",
                    "max_total_result_bytes": self.context.max_total_result_bytes,
                },
            )
        self._tool_calls += 1
        started = perf_counter()
        try:
            result = execute()
        except Exception as exc:
            result = ToolResult(
                tool_name=tool_key,
                ok=False,
                content=f"工具调用未执行：{type(exc).__name__}",
                metadata={"error_type": type(exc).__name__},
            )
        retained_bytes = int(result.metadata.get("retained_bytes", 0))
        self._retained_result_bytes += retained_bytes
        return replace(
            result,
            metadata={
                **result.metadata,
                "tool_call_index": self._tool_calls,
                "duration_ms": int((perf_counter() - started) * 1000),
                "total_retained_bytes": self._retained_result_bytes,
            },
        )

    def _result_budget(self, tool_key: str) -> int:
        configured = self.context.tool_configs.get(tool_key, {})
        configured_max = configured.get(
            "max_result_bytes", self.context.max_result_bytes
        )
        if isinstance(configured_max, bool):
            per_tool = self.context.max_result_bytes
        elif isinstance(configured_max, (int, float, str)):
            try:
                per_tool = max(1, int(configured_max))
            except (TypeError, ValueError):
                per_tool = self.context.max_result_bytes
        else:
            per_tool = self.context.max_result_bytes
        return min(per_tool, self._remaining_result_bytes())

    def _remaining_result_bytes(self) -> int:
        return max(self.context.max_total_result_bytes - self._retained_result_bytes, 0)

    def _record_tool_result(self, result: ToolResult) -> ToolResult:
        self.context.observation_port.record_tool_observation(
            ToolCallObservation(
                tool_name=result.tool_name,
                ok=result.ok,
                metadata=dict(result.metadata),
            )
        )
        return result


def _bounded(content: str, max_bytes: int) -> tuple[str, bool]:
    raw = content.encode("utf-8")
    if len(raw) <= max_bytes:
        return content, False
    envelope: dict[str, JsonValue] = {
        "truncated": True,
        "original_bytes": len(raw),
        "content": "",
    }
    overhead = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    retained_budget = max(max_bytes - overhead, 0)
    envelope["content"] = raw[:retained_budget].decode("utf-8", errors="ignore")
    bounded = json.dumps(envelope, ensure_ascii=False)
    content_value = envelope.get("content")
    while (
        len(bounded.encode("utf-8")) > max_bytes
        and isinstance(content_value, str)
        and content_value
    ):
        content_value = content_value[:-1]
        envelope["content"] = content_value
        bounded = json.dumps(envelope, ensure_ascii=False)
    return bounded, True
