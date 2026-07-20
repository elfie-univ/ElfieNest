from __future__ import annotations

from dataclasses import dataclass

from ai_runtime.tools.executor import ToolExecutionContext, ToolExecutor, ToolResult


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

    def verify_action(self, action: str, file_path: str, token: str | None = None) -> None:
        self.action = action
        self.file_path = file_path


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
                sandbox_plugin=sandbox_plugin,
                skills_evolution_plugin=skills_plugin,
                permission_manager=permission_manager,
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


def test_tool_executor_handles_code_with_permission_and_feedback_text():
    executor, _, sandbox_plugin, _, permission_manager = make_executor(("code_sandbox",))

    result = executor.execute("[CODE]print(2 + 2)[/CODE]")

    assert result is not None
    assert result.tool_name == "code_sandbox"
    assert result.ok is True
    assert sandbox_plugin.code == "print(2 + 2)"
    assert permission_manager.action == "RUN_CODE"
    assert permission_manager.file_path == "code_sandbox"
    assert "标准输出: 4" in result.content
    assert "去掉 [CODE] 标签" in result.content


def test_tool_executor_handles_write_skill_and_parse_error():
    executor, _, _, skills_plugin, _ = make_executor(("skills_evolution",))

    result = executor.execute("[WRITE_SKILL]math_tool|print('ok')[/WRITE_SKILL]")
    parse_error = executor.execute("[WRITE_SKILL]bad-format[/WRITE_SKILL]")

    assert result is not None
    assert result.tool_name == "write_skill"
    assert result.ok is True
    assert skills_plugin.skill_name == "math_tool"
    assert skills_plugin.skill_args == "print('ok')"
    assert result.content == "Skill written"

    assert parse_error is not None
    assert parse_error.tool_name == "write_skill"
    assert parse_error.ok is False
    assert "格式必须是 [WRITE_SKILL]文件名|Python代码[/WRITE_SKILL]" in parse_error.content


def test_tool_executor_handles_run_skill_success_and_failure_feedback():
    executor, _, _, skills_plugin, _ = make_executor(("skills_evolution",))

    success = executor.execute("[RUN_SKILL]math_tool|1,2[/RUN_SKILL]")

    assert success is not None
    assert success.tool_name == "run_skill"
    assert success.ok is True
    assert skills_plugin.skill_name == "math_tool"
    assert skills_plugin.skill_args == "1,2"
    assert "【习得技能 'math_tool' 运行成功】" in success.content
    assert "标准输出 (stdout): Skill output" in success.content

    skills_plugin.run_skill = lambda filename, args="": {
        "exit_code": 1,
        "stdout": "",
        "stderr": "boom",
    }
    failure = executor.execute("[RUN_SKILL]math_tool[/RUN_SKILL]")

    assert failure is not None
    assert failure.tool_name == "run_skill"
    assert failure.ok is False
    assert "【习得技能 'math_tool' 运行故障】" in failure.content
    assert "错误流 (stderr): boom" in failure.content


def test_tool_executor_handles_list_skills_and_ignores_disallowed_tags():
    executor, _, _, _, _ = make_executor(("skills_evolution",))
    disallowed, _, _, _, _ = make_executor(())

    result = executor.execute("[LIST_SKILLS][/LIST_SKILLS]")

    assert result is not None
    assert result.tool_name == "list_skills"
    assert result.ok is True
    assert result.content == "Skill list"
    assert disallowed.execute("[LIST_SKILLS][/LIST_SKILLS]") is None


def test_tool_executor_handles_controlled_local_file_access():
    executor, search, sandbox, skills, permission = make_executor(("local_file",))
    file_access = FakeFileAccessPlugin()
    executor.context = ToolExecutionContext(
        allowed_skills=("local_file",),
        search_plugin=search,
        sandbox_plugin=sandbox,
        skills_evolution_plugin=skills,
        permission_manager=permission,
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
