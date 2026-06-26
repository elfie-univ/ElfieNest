from dataclasses import dataclass

import pytest

from runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext


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

    def verify_action(self, action: str, file_path: str, token: str | None = None) -> None:
        self.action = action


@dataclass
class FakeSkillsPlugin:
    skill_name: str = ""

    def write_skill(
        self, filename: str, code: str, admin_token: str | None = None
    ) -> str:
        self.skill_name = filename
        return "Skill written"

    def run_skill(self, filename: str, args: str = "") -> dict[str, str | int]:
        self.skill_name = filename
        return {"exit_code": 0, "stdout": "Skill output", "stderr": ""}

    def list_skills(self) -> str:
        return "Skill list"


def test_runtime_tool_loop_runs_search_then_returns_final_response():
    search_plugin = FakeSearchPlugin()
    messages = [{"role": "user", "content": "What is ElfieNest?"}]
    context = ToolLoopContext(
        allowed_skills=("web_search",),
        search_plugin=search_plugin,
        sandbox_plugin=FakeSandboxPlugin(),
        skills_evolution_plugin=FakeSkillsPlugin(),
        permission_manager=FakePermissionManager(),
    )
    loop = RuntimeToolLoop(context)
    responses = iter(["[SEARCH]ElfieNest[/SEARCH]", "Final answer"])

    result = loop.run(
        messages=messages,
        max_loops=2,
        call_llm=lambda messages: next(responses),
    )

    assert result == "Final answer"
    assert search_plugin.query == "ElfieNest"
    assert messages[-2] == {"role": "assistant", "content": "[SEARCH]ElfieNest[/SEARCH]"}
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"].startswith("【联网搜索反馈】")


def test_runtime_tool_loop_runs_code_sandbox_with_permission_check():
    sandbox_plugin = FakeSandboxPlugin()
    permission_manager = FakePermissionManager()
    context = ToolLoopContext(
        allowed_skills=("code_sandbox",),
        search_plugin=FakeSearchPlugin(),
        sandbox_plugin=sandbox_plugin,
        skills_evolution_plugin=FakeSkillsPlugin(),
        permission_manager=permission_manager,
    )
    loop = RuntimeToolLoop(context)
    responses = iter(["[CODE]print(2 + 2)[/CODE]", "Final answer"])

    result = loop.run(
        messages=[{"role": "user", "content": "2+2?"}],
        max_loops=2,
        call_llm=lambda messages: next(responses),
    )

    assert result == "Final answer"
    assert sandbox_plugin.code == "print(2 + 2)"
    assert permission_manager.action == "RUN_CODE"


def test_runtime_tool_loop_times_out_when_model_keeps_requesting_tools():
    context = ToolLoopContext(
        allowed_skills=("web_search",),
        search_plugin=FakeSearchPlugin(),
        sandbox_plugin=FakeSandboxPlugin(),
        skills_evolution_plugin=FakeSkillsPlugin(),
        permission_manager=FakePermissionManager(),
    )
    loop = RuntimeToolLoop(context)

    with pytest.raises(TimeoutError):
        loop.run(
            messages=[{"role": "user", "content": "Search"}],
            max_loops=1,
            call_llm=lambda messages: "[SEARCH]again[/SEARCH]",
        )
