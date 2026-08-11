"""Semantic tool loop backed by the Brain-owned ToolPort."""

from __future__ import annotations

from collections.abc import Callable

from elfie.brain.tool_port import ToolPort, ToolRequest
from elfie.message_types import ElfieId


class PortToolLoop:
    """Translate model tool markers into the injected semantic ToolPort."""

    def __init__(
        self,
        tool_port: ToolPort,
        *,
        allowed_tool_keys: tuple[str, ...],
        scope_id: str | None,
    ) -> None:
        self._tool_port = tool_port
        self._allowed_tool_keys = allowed_tool_keys
        self._scope_id = scope_id

    def run(
        self,
        messages: list[dict[str, str]],
        max_loops: int,
        call_llm: Callable[[list[dict[str, str]]], str],
    ) -> str:
        for _loop_idx in range(max_loops):
            response_text = call_llm(messages)
            request = _parse_port_request(response_text, scope_id=self._scope_id)
            if request is None or request.tool_key not in self._allowed_tool_keys:
                return response_text
            result = self._tool_port.execute(request)
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": result.content})
        raise TimeoutError("❌ 工具语义循环超过本次请求的迭代上限。")


def _parse_port_request(
    response_text: str,
    *,
    scope_id: str | None,
) -> ToolRequest | None:
    typed_scope_id = ElfieId(scope_id) if scope_id is not None else None
    if _has_tag(response_text, "SEARCH"):
        query = _extract_tag(response_text, "SEARCH")
        if not query:
            return None
        return ToolRequest(
            scope_id=typed_scope_id,
            tool_key="web_search",
            operation="search",
            query=query,
        )
    if _has_tag(response_text, "READ_FILE"):
        resource_id = _extract_tag(response_text, "READ_FILE")
        if not resource_id or scope_id is None:
            return None
        return ToolRequest(
            scope_id=typed_scope_id,
            tool_key="local_file",
            operation="read",
            resource_id=resource_id,
        )
    if _has_tag(response_text, "LIST_FILES"):
        if scope_id is None:
            return None
        resource_id = _extract_tag(response_text, "LIST_FILES") or "."
        return ToolRequest(
            scope_id=typed_scope_id,
            tool_key="local_file",
            operation="list",
            resource_id=resource_id,
        )
    return None


def _has_tag(text: str, tag_name: str) -> bool:
    return f"[{tag_name}]" in text and f"[/{tag_name}]" in text


def _extract_tag(text: str, tag_name: str) -> str:
    return text.split(f"[{tag_name}]")[1].split(f"[/{tag_name}]")[0].strip()


__all__ = ["PortToolLoop"]
