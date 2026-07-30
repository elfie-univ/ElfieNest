from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Dict, Protocol, Union

from ai_runtime.usage.observer import (
    RuntimeEventStatus,
    ToolCallObservation,
    get_runtime_observer,
)

logger = logging.getLogger("ai_runtime.tools.executor")

ToolMetadataValue = Union[str, int, bool]
ToolData = Dict[str, ToolMetadataValue]


class SearchPlugin(Protocol):
    def search(self, query: str) -> str: ...


class PermissionManager(Protocol):
    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None: ...


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
    owner_token: str | None = None
    file_access_plugin: FileAccessPlugin | None = None
    max_result_bytes: int = 16000


class ToolExecutor:
    def __init__(self, context: ToolExecutionContext):
        self.context = context

    def execute(self, response_text: str) -> ToolResult | None:
        if self._can_use("local_file") and _has_tag(response_text, "READ_FILE"):
            return self._record_tool_result(self._execute_read_file(response_text))

        if self._can_use("local_file") and _has_tag(response_text, "LIST_FILES"):
            return self._record_tool_result(self._execute_list_files(response_text))

        if self._can_use("web_search") and _has_tag(response_text, "SEARCH"):
            return self._record_tool_result(self._execute_search(response_text))

        return None

    def _execute_read_file(self, response_text: str) -> ToolResult:
        path = _extract_tag(response_text, "READ_FILE")
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult("local_file_read", False, "本地文件工具未配置")
        self.context.permission_manager.verify_action("READ", file_path=path)
        content = plugin.read_text(path)
        bounded, truncated = _bounded(content, self.context.max_result_bytes)
        return ToolResult(
            tool_name="local_file_read",
            ok=True,
            content=(
                f"【本地文件 {path} 内容】\n{bounded}\n"
                "请根据文件内容生成最终回答，去掉 [READ_FILE] 标签。"
            ),
            metadata={
                "path": path,
                "truncated": truncated,
                "bytes": len(content.encode("utf-8")),
                "retained_bytes": len(bounded.encode("utf-8")),
            },
        )

    def _execute_list_files(self, response_text: str) -> ToolResult:
        path = _extract_tag(response_text, "LIST_FILES") or "."
        plugin = self.context.file_access_plugin
        if plugin is None:
            return ToolResult("local_file_list", False, "本地文件工具未配置")
        self.context.permission_manager.verify_action("READ", file_path=path)
        files = plugin.list_files(path)
        payload, truncated = _bounded("\n".join(files), self.context.max_result_bytes)
        return ToolResult(
            tool_name="local_file_list",
            ok=True,
            content=(
                f"【本地目录 {path} 文件】\n"
                + payload
                + "\n请根据文件清单生成最终回答，去掉 [LIST_FILES] 标签。"
            ),
            metadata={
                "path": path,
                "truncated": truncated,
                "items": len(files),
                "retained_items": len(payload.splitlines()) if payload else 0,
            },
        )

    def _can_use(self, skill_name: str) -> bool:
        return skill_name in self.context.allowed_skills

    def _execute_search(self, response_text: str) -> ToolResult:
        query = _extract_tag(response_text, "SEARCH")
        self.context.permission_manager.verify_action(
            "WEB_SEARCH", file_path=query[:120]
        )
        search_result = self.context.search_plugin.search(query)
        bounded, truncated = _bounded(search_result, self.context.max_result_bytes)
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
                "query": query,
                "truncated": truncated,
                "bytes": len(search_result.encode("utf-8")),
                "retained_bytes": len(bounded.encode("utf-8")),
            },
        )

    def _record_tool_result(self, result: ToolResult) -> ToolResult:
        get_runtime_observer().record_tool_call(
            ToolCallObservation(
                tool_name=result.tool_name,
                status=RuntimeEventStatus.OK if result.ok else RuntimeEventStatus.ERROR,
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
    envelope = {
        "truncated": True,
        "original_bytes": len(raw),
        "content": "",
    }
    overhead = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    retained_budget = max(max_bytes - overhead, 0)
    envelope["content"] = raw[:retained_budget].decode("utf-8", errors="ignore")
    bounded = json.dumps(envelope, ensure_ascii=False)
    while len(bounded.encode("utf-8")) > max_bytes and envelope["content"]:
        envelope["content"] = envelope["content"][:-1]
        bounded = json.dumps(envelope, ensure_ascii=False)
    return bounded, True
