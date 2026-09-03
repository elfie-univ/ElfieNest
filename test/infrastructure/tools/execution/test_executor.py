from __future__ import annotations

from dataclasses import dataclass, field

from elfie.brain.reasoning.tool_port import ToolRequest
from infrastructure.tools.execution.executor import (
    ToolExecutionContext,
    ToolExecutor,
    ToolResult,
)
from infrastructure.tools.execution.observation import (
    PermissionDecisionObservation,
    ToolCallObservation,
)


@dataclass
class FakeSearchPlugin:
    query: str = ""

    def search(self, query: str) -> str:
        self.query = query
        return "Search result"


@dataclass
class FakePermissionManager:
    actions: list[str] = field(default_factory=list)

    def verify_action(
        self, action: str, file_path: str | None = None, token: str | None = None
    ) -> bool:
        del file_path, token
        self.actions.append(action)
        return True


@dataclass
class DenyingPermissionManager(FakePermissionManager):
    def verify_action(
        self, action: str, file_path: str | None = None, token: str | None = None
    ) -> bool:
        super().verify_action(action, file_path, token)
        raise PermissionError("policy denied")


@dataclass
class FakeObservationPort:
    tool_calls: list[ToolCallObservation] = field(default_factory=list)
    permission_decisions: list[PermissionDecisionObservation] = field(
        default_factory=list
    )

    def record_tool_observation(self, observation: ToolCallObservation) -> None:
        self.tool_calls.append(observation)

    def record_permission_observation(
        self, observation: PermissionDecisionObservation
    ) -> None:
        self.permission_decisions.append(observation)


@dataclass
class FakeFileAccessPlugin:
    path: str = ""

    def read_text(self, relative_path: str) -> str:
        self.path = relative_path
        return "local content"

    def list_files(self, relative_path: str = ".") -> list[str]:
        self.path = relative_path
        return ["one.txt", "two.txt"]


def make_executor(
    allowed_tool_keys: tuple[str, ...],
    *,
    runtime_enabled_tools: tuple[str, ...] = ("web_search", "local_file"),
    permission_manager: FakePermissionManager | None = None,
) -> tuple[ToolExecutor, FakeSearchPlugin, FakeObservationPort, FakePermissionManager]:
    search_plugin = FakeSearchPlugin()
    observation_port = FakeObservationPort()
    permissions = permission_manager or FakePermissionManager()
    return (
        ToolExecutor(
            ToolExecutionContext(
                allowed_tool_keys=allowed_tool_keys,
                runtime_enabled_tools=runtime_enabled_tools,
                search_plugin=search_plugin,
                permission_manager=permissions,
                observation_port=observation_port,
            )
        ),
        search_plugin,
        observation_port,
        permissions,
    )


def test_tool_result_carries_tool_name_status_content_and_metadata():
    result = ToolResult(
        tool_name="web_search",
        ok=True,
        content="feedback",
        metadata={"query": "ElfieNest"},
    )

    assert result.tool_name == "web_search"
    assert result.ok is True
    assert result.content == "feedback"
    assert result.metadata == {"query": "ElfieNest"}


def test_tool_executor_handles_typed_search_request_without_text_markers():
    executor, search_plugin, observation_port, _ = make_executor(("web_search",))

    result = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="ElfieNest")
    )

    assert result.ok is True
    assert search_plugin.query == "ElfieNest"
    assert result.content.startswith("【联网搜索反馈】")
    assert "Search result" in result.content
    assert observation_port.tool_calls[-1].tool_name == "web_search"


def test_tool_executor_handles_controlled_local_file_access():
    executor, _, _, permission = make_executor(("local_file",))
    file_access = FakeFileAccessPlugin()
    executor.context = ToolExecutionContext(
        allowed_tool_keys=("local_file",),
        search_plugin=FakeSearchPlugin(),
        permission_manager=permission,
        observation_port=FakeObservationPort(),
        file_access_plugin=file_access,
    )

    read_result = executor.execute(
        ToolRequest(
            scope_id="elfie-1",
            tool_key="local_file",
            operation="read",
            resource_id="notes/probe.txt",
        )
    )
    list_result = executor.execute(
        ToolRequest(
            scope_id="elfie-1",
            tool_key="local_file",
            operation="list",
            resource_id="notes",
        )
    )

    assert read_result.ok is True
    assert read_result.tool_name == "local_file"
    assert "local content" in read_result.content
    assert list_result.ok is True
    assert "one.txt" in list_result.content
    assert file_access.path == "notes"
    assert permission.actions == ["READ", "READ"]


def test_tool_executor_requires_runtime_request_and_safe_implementation_intersection():
    executor, search, _, _ = make_executor(("web_search",), runtime_enabled_tools=())

    result = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="ElfieNest")
    )

    assert result.ok is False
    assert result.metadata["error_type"] == "tool_denied"
    assert search.query == ""


def test_tool_executor_refuses_unknown_tool_even_if_requested():
    executor, search, _, permission = make_executor(("code_sandbox",))

    result = executor.execute(
        ToolRequest(
            scope_id="elfie-1",
            tool_key="code_sandbox",
            operation="read",
            resource_id="code.py",
        )
    )

    assert result.ok is False
    assert result.metadata["error_type"] == "tool_denied"
    assert search.query == ""
    assert permission.actions == []


def test_tool_executor_returns_safe_feedback_when_permission_denies_a_tool():
    search = FakeSearchPlugin()
    permission = DenyingPermissionManager()
    executor, _, _, _ = make_executor(("web_search",), permission_manager=permission)

    result = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="ElfieNest")
    )

    assert result.ok is False
    assert result.metadata["error_type"] == "PermissionError"
    assert search.query == ""


def test_tool_executor_enforces_the_total_result_budget_across_tool_calls():
    search = FakeSearchPlugin()
    executor, _, _, _ = make_executor(("web_search",))
    executor.context = ToolExecutionContext(
        allowed_tool_keys=("web_search",),
        search_plugin=search,
        permission_manager=FakePermissionManager(),
        observation_port=FakeObservationPort(),
        max_total_result_bytes=len(b"Search result"),
        tool_configs={"web_search": {"max_result_bytes": 100}},
    )

    first = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="first")
    )
    second = executor.execute(
        ToolRequest(tool_key="web_search", operation="search", query="second")
    )

    assert first.ok is True
    assert second.ok is False
    assert second.metadata["limit"] == "total_result_bytes"
    assert search.query == "first"
