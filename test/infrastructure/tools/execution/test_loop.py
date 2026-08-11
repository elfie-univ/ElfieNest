from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from elfie.brain.tool_port import ToolKey, ToolRequest, ToolResult
from elfie.message_types import ErrorInfo
from infrastructure.tools.execution.loop import PortToolLoop


@dataclass
class FakeToolPort:
    requests: list[ToolRequest] = field(default_factory=list)

    def available_tool_keys(self) -> tuple[ToolKey, ...]:
        return ("web_search", "local_file")

    def execute(self, request: ToolRequest) -> ToolResult:
        self.requests.append(request)
        if request.tool_key == "web_search":
            return ToolResult(
                tool_key=request.tool_key, ok=True, content="Search result"
            )
        if request.operation == "read":
            return ToolResult(
                tool_key=request.tool_key, ok=True, content="private content"
            )
        return ToolResult(
            tool_key=request.tool_key,
            ok=False,
            content="denied",
            error=ErrorInfo(code="denied", message="denied"),
        )


def test_port_tool_loop_runs_search_then_returns_final_response():
    tool_port = FakeToolPort()
    messages = [{"role": "user", "content": "What is ElfieNest?"}]
    loop = PortToolLoop(
        tool_port, allowed_tool_keys=("web_search",), scope_id="elfie-1"
    )
    responses = iter(["[SEARCH]ElfieNest[/SEARCH]", "Final answer"])

    result = loop.run(messages, 2, lambda _messages: next(responses))

    assert result == "Final answer"
    assert tool_port.requests == [
        ToolRequest(
            scope_id="elfie-1",
            tool_key="web_search",
            operation="search",
            query="ElfieNest",
        )
    ]
    assert messages[-1]["content"] == "Search result"


def test_port_tool_loop_scopes_local_file_requests_to_the_semantic_port():
    tool_port = FakeToolPort()
    messages = [{"role": "user", "content": "read"}]
    loop = PortToolLoop(
        tool_port, allowed_tool_keys=("local_file",), scope_id="elfie-1"
    )
    responses = iter(["[READ_FILE]private/notes.txt[/READ_FILE]", "final"])

    assert loop.run(messages, 2, lambda _messages: next(responses)) == "final"
    assert tool_port.requests[0].resource_id == "private/notes.txt"
    assert messages[-1]["content"] == "private content"


def test_port_tool_loop_does_not_execute_unapproved_markers():
    tool_port = FakeToolPort()
    loop = PortToolLoop(
        tool_port, allowed_tool_keys=("web_search",), scope_id="elfie-1"
    )

    result = loop.run(
        messages=[{"role": "user", "content": "2+2?"}],
        max_loops=2,
        call_llm=lambda _messages: "[CODE]print(2 + 2)[/CODE]",
    )

    assert result == "[CODE]print(2 + 2)[/CODE]"
    assert tool_port.requests == []


def test_port_tool_loop_does_not_execute_unscoped_local_file_marker():
    tool_port = FakeToolPort()
    loop = PortToolLoop(tool_port, allowed_tool_keys=("local_file",), scope_id=None)

    result = loop.run(
        messages=[{"role": "user", "content": "read"}],
        max_loops=2,
        call_llm=lambda _messages: "[READ_FILE]private/notes.txt[/READ_FILE]",
    )

    assert result == "[READ_FILE]private/notes.txt[/READ_FILE]"
    assert tool_port.requests == []


def test_port_tool_loop_times_out_when_model_keeps_requesting_tools():
    tool_port = FakeToolPort()
    loop = PortToolLoop(
        tool_port, allowed_tool_keys=("web_search",), scope_id="elfie-1"
    )

    with pytest.raises(TimeoutError):
        loop.run(
            messages=[{"role": "user", "content": "Search"}],
            max_loops=1,
            call_llm=lambda _messages: "[SEARCH]again[/SEARCH]",
        )
