from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Callable, Protocol

from pydantic import JsonValue

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
    allowed_skills: tuple[str, ...]
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

    def execute(self, response_text: str) -> ToolResult | None:
        if self._can_use("local_file") and _has_tag(response_text, "READ_FILE"):
            return self._record_tool_result(
                self._execute_with_guard(
                    "local_file", lambda: self._execute_read_file(response_text)
                )
            )

        if self._can_use("local_file") and _has_tag(response_text, "LIST_FILES"):
            return self._record_tool_result(
                self._execute_with_guard(
                    "local_file", lambda: self._execute_list_files(response_text)
                )
            )

        if self._can_use("web_search") and _has_tag(response_text, "SEARCH"):
            return self._record_tool_result(
                self._execute_with_guard(
                    "web_search", lambda: self._execute_search(response_text)
                )
            )

        return None

    def _execute_read_file(self, response_text: str) -> ToolResult:
        path = _extract_tag(response_text, "READ_FILE")
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult("local_file_read", False, "本地文件工具未配置")
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
            tool_name="local_file_read",
            ok=True,
            content=(
                f"【本地文件内容】\n{bounded}\n"
                "请根据文件内容生成最终回答，去掉 [READ_FILE] 标签。"
            ),
            metadata={
                "truncated": source_truncated or envelope_truncated,
                "bytes": source_bytes,
                "retained_bytes": len(bounded.encode("utf-8")),
            },
        )

    def _execute_list_files(self, response_text: str) -> ToolResult:
        path = _extract_tag(response_text, "LIST_FILES") or "."
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult("local_file_list", False, "本地文件工具未配置")
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
            tool_name="local_file_list",
            ok=True,
            content=(
                "【本地目录文件】\n"
                + payload
                + "\n请根据文件清单生成最终回答，去掉 [LIST_FILES] 标签。"
            ),
            metadata={
                "truncated": source_truncated or envelope_truncated,
                "items": source_items,
                "retained_items": len(payload.splitlines()) if payload else 0,
            },
        )

    def _can_use(self, skill_name: str) -> bool:
        return (
            skill_name in SAFE_TOOL_KEYS
            and skill_name in self.context.allowed_skills
            and skill_name in self.context.runtime_enabled_tools
        )

    def _execute_search(self, response_text: str) -> ToolResult:
        query = _extract_tag(response_text, "SEARCH")
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
            content=(
                "【联网搜索反馈】\n"
                "结合以下最新网络检索事实数据，修正并生成最终回答，去掉 [SEARCH] 标签：\n"
                f"{bounded}"
            ),
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


def _has_tag(text: str, tag_name: str) -> bool:
    return f"[{tag_name}]" in text and f"[/{tag_name}]" in text


def _extract_tag(text: str, tag_name: str) -> str:
    return text.split(f"[{tag_name}]")[1].split(f"[/{tag_name}]")[0].strip()


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
