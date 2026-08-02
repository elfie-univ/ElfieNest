from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext


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

    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None:
        self.action = action


@dataclass
class FakeSkillsPlugin:
    skill_name: str = ""

    def write_skill(
        self, filename: str, code: str, owner_token: str | None = None
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
    assert messages[-2] == {
        "role": "assistant",
        "content": "[SEARCH]ElfieNest[/SEARCH]",
    }
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"].startswith("【联网搜索反馈】")


def test_runtime_tool_loop_does_not_echo_local_workspace_paths_to_the_model():
    class FileAccess:
        def read_text(self, relative_path: str) -> str:
            assert relative_path == "private/notes.txt"
            return "private content"

        def list_files(self, relative_path: str = ".") -> list[str]:
            return []

    messages = [{"role": "user", "content": "read"}]
    loop = RuntimeToolLoop(
        ToolLoopContext(
            allowed_skills=("local_file",),
            search_plugin=FakeSearchPlugin(),
            permission_manager=FakePermissionManager(),
            file_access_plugin=FileAccess(),
        )
    )
    responses = iter(["[READ_FILE]private/notes.txt[/READ_FILE]", "final"])

    assert loop.run(messages, 2, lambda _messages: next(responses)) == "final"
    assert "private/notes.txt" not in messages[-1]["content"]


def test_runtime_tool_loop_does_not_run_unavailable_code_sandbox():
    sandbox_plugin = FakeSandboxPlugin()
    permission_manager = FakePermissionManager()
    context = ToolLoopContext(
        allowed_skills=("code_sandbox",),
        search_plugin=FakeSearchPlugin(),
        permission_manager=permission_manager,
    )
    loop = RuntimeToolLoop(context)
    result = loop.run(
        messages=[{"role": "user", "content": "2+2?"}],
        max_loops=2,
        call_llm=lambda messages: "[CODE]print(2 + 2)[/CODE]",
    )

    assert result == "[CODE]print(2 + 2)[/CODE]"
    assert sandbox_plugin.code == ""
    assert permission_manager.action == ""


def test_runtime_tool_loop_times_out_when_model_keeps_requesting_tools():
    context = ToolLoopContext(
        allowed_skills=("web_search",),
        search_plugin=FakeSearchPlugin(),
        permission_manager=FakePermissionManager(),
    )
    loop = RuntimeToolLoop(context)

    with pytest.raises(TimeoutError):
        loop.run(
            messages=[{"role": "user", "content": "Search"}],
            max_loops=1,
            call_llm=lambda messages: "[SEARCH]again[/SEARCH]",
        )
