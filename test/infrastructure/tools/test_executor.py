from __future__ import annotations

from dataclasses import dataclass, field

from infrastructure.tools.executor import ToolExecutionContext, ToolExecutor, ToolResult
from infrastructure.tools.observation import (
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
class FakeSandboxPlugin:
    code: str = ""

    def execute(self, code: str) -> dict[str, str | int]:
        self.code = code
        return {"stdout": "4", "stderr": "", "exit_code": 0}


@dataclass
class FakePermissionManager:
    action: str = ""
    file_path: str = ""

    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None:
        self.action = action
        self.file_path = file_path


@dataclass
class DenyingPermissionManager(FakePermissionManager):
    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None:
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
class FakeSkillsPlugin:
    skill_name: str = ""
    skill_args: str = ""

    def write_skill(
        self, filename: str, code: str, owner_token: str | None = None
    ) -> str:
        self.skill_name = filename
        self.skill_args = code
        return "Skill written"

    def run_skill(self, filename: str, args: str = "") -> dict[str, str | int]:
        self.skill_name = filename
        self.skill_args = args
        return {"exit_code": 0, "stdout": "Skill output", "stderr": ""}

    def list_skills(self) -> str:
        return "Skill list"


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
    allowed_skills: tuple[str, ...],
) -> tuple[
    ToolExecutor,
    FakeSearchPlugin,
    FakeSandboxPlugin,
    FakeSkillsPlugin,
    FakePermissionManager,
]:
    search_plugin = FakeSearchPlugin()
    sandbox_plugin = FakeSandboxPlugin()
    skills_plugin = FakeSkillsPlugin()
    permission_manager = FakePermissionManager()
    return (
        ToolExecutor(
            ToolExecutionContext(
                allowed_skills=allowed_skills,
                search_plugin=search_plugin,
                permission_manager=permission_manager,
                observation_port=FakeObservationPort(),
            )
        ),
        search_plugin,
        sandbox_plugin,
        skills_plugin,
        permission_manager,
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


def test_tool_executor_handles_search_and_preserves_feedback_text():
    executor, search_plugin, _, _, _ = make_executor(("web_search",))

    result = executor.execute("[SEARCH]ElfieNest[/SEARCH]")

    assert result is not None
    assert result.tool_name == "web_search"
    assert result.ok is True
    assert search_plugin.query == "ElfieNest"
    assert result.content.startswith("【联网搜索反馈】")
    assert "去掉 [SEARCH] 标签" in result.content
    assert "Search result" in result.content


def test_tool_executor_ignores_code_sandbox_tags():
    executor, _, sandbox_plugin, _, permission_manager = make_executor(
        ("code_sandbox",)
    )

    result = executor.execute("[CODE]print(2 + 2)[/CODE]")

    assert result is None
    assert sandbox_plugin.code == ""
    assert permission_manager.action == ""


def test_tool_executor_ignores_skill_mutation_tags():
    executor, _, _, skills_plugin, _ = make_executor(("skills_evolution",))

    result = executor.execute("[WRITE_SKILL]math_tool|print('ok')[/WRITE_SKILL]")
    parse_error = executor.execute("[WRITE_SKILL]bad-format[/WRITE_SKILL]")

    assert result is None
    assert parse_error is None
    assert skills_plugin.skill_name == ""


def test_tool_executor_ignores_skill_execution_tags():
    executor, _, _, skills_plugin, _ = make_executor(("skills_evolution",))

    success = executor.execute("[RUN_SKILL]math_tool|1,2[/RUN_SKILL]")

    assert success is None
    assert skills_plugin.skill_name == ""

    skills_plugin.run_skill = lambda filename, args="": {
        "exit_code": 1,
        "stdout": "",
        "stderr": "boom",
    }
    failure = executor.execute("[RUN_SKILL]math_tool[/RUN_SKILL]")

    assert failure is None


def test_tool_executor_ignores_list_skills_tags():
    executor, _, _, _, _ = make_executor(("skills_evolution",))
    disallowed, _, _, _, _ = make_executor(())

    result = executor.execute("[LIST_SKILLS][/LIST_SKILLS]")

    assert result is None
    assert disallowed.execute("[LIST_SKILLS][/LIST_SKILLS]") is None


def test_tool_executor_handles_controlled_local_file_access():
    executor, search, sandbox, skills, permission = make_executor(("local_file",))
    file_access = FakeFileAccessPlugin()
    executor.context = ToolExecutionContext(
        allowed_skills=("local_file",),
        search_plugin=search,
        permission_manager=permission,
        observation_port=FakeObservationPort(),
        file_access_plugin=file_access,
    )

    read_result = executor.execute("[READ_FILE]notes/probe.txt[/READ_FILE]")
    list_result = executor.execute("[LIST_FILES]notes[/LIST_FILES]")

    assert read_result is not None
    assert read_result.tool_name == "local_file_read"
    assert "local content" in read_result.content
    assert list_result is not None
    assert list_result.tool_name == "local_file_list"
    assert "one.txt" in list_result.content
    assert "notes/probe.txt" not in read_result.content
    assert "notes" not in list_result.content
    assert "path" not in read_result.metadata
    assert "path" not in list_result.metadata


def test_tool_executor_requires_runtime_request_and_safe_implementation_intersection():
    executor, search, _, _, _ = make_executor(("web_search",))
    executor.context = ToolExecutionContext(
        allowed_skills=("web_search",),
        runtime_enabled_tools=(),
        search_plugin=search,
        permission_manager=FakePermissionManager(),
        observation_port=FakeObservationPort(),
    )

    assert executor.execute("[SEARCH]ElfieNest[/SEARCH]") is None
    assert search.query == ""


def test_tool_executor_still_refuses_unsafe_tools_when_all_callers_request_them():
    executor, _, sandbox, _, permission = make_executor(("code_sandbox",))
    executor.context = ToolExecutionContext(
        allowed_skills=("code_sandbox",),
        runtime_enabled_tools=("code_sandbox",),
        search_plugin=FakeSearchPlugin(),
        permission_manager=permission,
        observation_port=FakeObservationPort(),
    )

    assert executor.execute("[CODE]print(2 + 2)[/CODE]") is None
    assert sandbox.code == ""
    assert permission.action == ""


def test_tool_executor_returns_safe_feedback_when_permission_denies_a_tool():
    search = FakeSearchPlugin()
    permission = DenyingPermissionManager()
    executor = ToolExecutor(
        ToolExecutionContext(
            allowed_skills=("web_search",),
            search_plugin=search,
            permission_manager=permission,
            observation_port=FakeObservationPort(),
        )
    )

    result = executor.execute("[SEARCH]ElfieNest[/SEARCH]")

    assert result is not None
    assert result.ok is False
    assert result.metadata["error_type"] == "PermissionError"
    assert search.query == ""


def test_tool_executor_enforces_the_total_result_budget_across_tool_calls():
    search = FakeSearchPlugin()
    executor = ToolExecutor(
        ToolExecutionContext(
            allowed_skills=("web_search",),
            search_plugin=search,
            permission_manager=FakePermissionManager(),
            observation_port=FakeObservationPort(),
            max_total_result_bytes=len(b"Search result"),
            tool_configs={"web_search": {"max_result_bytes": 100}},
        )
    )

    first = executor.execute("[SEARCH]first[/SEARCH]")
    second = executor.execute("[SEARCH]second[/SEARCH]")

    assert first is not None
    assert first.ok is True
    assert second is not None
    assert second.ok is False
    assert second.metadata["limit"] == "total_result_bytes"
    assert search.query == "first"
