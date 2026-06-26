import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias

from runtime.usage.observer import (
    RuntimeEventStatus,
    ToolCallObservation,
    get_runtime_observer,
)

logger = logging.getLogger("runtime.tools.executor")

ToolMetadataValue: TypeAlias = str | int | bool
ToolData: TypeAlias = dict[str, str | int | bool]


class SearchPlugin(Protocol):
    def search(self, query: str) -> str: ...


class SandboxPlugin(Protocol):
    def execute(self, code: str) -> ToolData: ...


class SkillsEvolutionPlugin(Protocol):
    def write_skill(
        self, filename: str, code: str, admin_token: str | None = None
    ) -> str: ...

    def run_skill(self, filename: str, args: str = "") -> ToolData: ...

    def list_skills(self) -> str: ...


class PermissionManager(Protocol):
    def verify_action(
        self, action: str, file_path: str, token: str | None = None
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    ok: bool
    content: str
    metadata: Mapping[str, ToolMetadataValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    allowed_skills: tuple[str, ...]
    search_plugin: SearchPlugin
    sandbox_plugin: SandboxPlugin
    skills_evolution_plugin: SkillsEvolutionPlugin
    permission_manager: PermissionManager
    admin_token: str | None = None


class ToolExecutor:
    def __init__(self, context: ToolExecutionContext):
        self.context = context

    def execute(self, response_text: str) -> ToolResult | None:
        if self._can_use("web_search") and _has_tag(response_text, "SEARCH"):
            return self._record_tool_result(self._execute_search(response_text))

        if self._can_use("code_sandbox") and _has_tag(response_text, "CODE"):
            return self._record_tool_result(self._execute_code(response_text))

        if self._can_use("skills_evolution") and _has_tag(
            response_text, "WRITE_SKILL"
        ):
            return self._record_tool_result(self._execute_write_skill(response_text))

        if self._can_use("skills_evolution") and _has_tag(response_text, "RUN_SKILL"):
            return self._record_tool_result(self._execute_run_skill(response_text))

        if self._can_use("skills_evolution") and _has_tag(response_text, "LIST_SKILLS"):
            return self._record_tool_result(self._execute_list_skills())

        return None

    def _can_use(self, skill_name: str) -> bool:
        return skill_name in self.context.allowed_skills

    def _execute_search(self, response_text: str) -> ToolResult:
        query = _extract_tag(response_text, "SEARCH")
        search_result = self.context.search_plugin.search(query)
        logger.info("已成功回调联网检索数据。")
        return ToolResult(
            tool_name="web_search",
            ok=True,
            content=(
                "【联网搜索反馈】\n"
                "结合以下最新网络检索事实数据，修正并生成最终回答，去掉 [SEARCH] 标签：\n"
                f"{search_result}"
            ),
            metadata={"query": query},
        )

    def _execute_code(self, response_text: str) -> ToolResult:
        code = _extract_tag(response_text, "CODE")
        self.context.permission_manager.verify_action(
            "RUN_SKILL", file_path="code_sandbox"
        )
        execution_result = self.context.sandbox_plugin.execute(code)
        logger.info("已成功回调沙箱算术运算结果。")
        return ToolResult(
            tool_name="code_sandbox",
            ok=True,
            content=(
                "【Python 沙箱执行反馈】\n"
                f"标准输出: {execution_result['stdout']}\n"
                "请基于上述代码计算的精确物理结果，修改并生成你最终、可信的完整回答，去掉 [CODE] 标签。"
            ),
            metadata={"code": code},
        )

    def _execute_write_skill(self, response_text: str) -> ToolResult:
        raw_block = _extract_tag(response_text, "WRITE_SKILL")
        if "|" not in raw_block:
            logger.info("技能沉淀标签解析失败。")
            return ToolResult(
                tool_name="write_skill",
                ok=False,
                content="❌ 语法解析错误：[WRITE_SKILL] 格式必须是 [WRITE_SKILL]文件名|Python代码[/WRITE_SKILL]",
            )

        skill_name, skill_code = raw_block.split("|", 1)
        normalized_name = skill_name.strip()
        feedback = self.context.skills_evolution_plugin.write_skill(
            normalized_name,
            skill_code.strip(),
            self.context.admin_token,
        )
        logger.info("已完成技能沉淀拦截与回调。")
        return ToolResult(
            tool_name="write_skill",
            ok=True,
            content=feedback,
            metadata={"skill_name": normalized_name},
        )

    def _execute_run_skill(self, response_text: str) -> ToolResult:
        raw_block = _extract_tag(response_text, "RUN_SKILL")
        if "|" in raw_block:
            skill_name, skill_args = raw_block.split("|", 1)
            normalized_name = skill_name.strip()
            normalized_args = skill_args.strip()
        else:
            normalized_name = raw_block.strip()
            normalized_args = ""

        run_result = self.context.skills_evolution_plugin.run_skill(
            normalized_name, normalized_args
        )
        exit_code = run_result["exit_code"]
        ok = exit_code == 0
        logger.info("已完成技能运行拦截与回调。")

        if ok:
            content = (
                f"【习得技能 '{normalized_name}' 运行成功】\n"
                f"标准输出 (stdout): {run_result['stdout']}\n"
                "请根据此结果重新生成你最终的文本回复，去掉 [RUN_SKILL] 标签。"
            )
        else:
            content = (
                f"【习得技能 '{normalized_name}' 运行故障】\n"
                f"错误流 (stderr): {run_result['stderr']}\n"
                "请根据此错误日志进行反思并重新回答。"
            )

        return ToolResult(
            tool_name="run_skill",
            ok=ok,
            content=content,
            metadata={"skill_name": normalized_name},
        )

    def _execute_list_skills(self) -> ToolResult:
        feedback = self.context.skills_evolution_plugin.list_skills()
        logger.info("已完成技能库检索与回调。")
        return ToolResult(
            tool_name="list_skills",
            ok=True,
            content=feedback,
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
