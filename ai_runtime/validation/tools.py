"""Runtime Agent 基础工具的直接验证。"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from ai_runtime.safety.permissions import PermissionDeniedError, PermissionManager
from ai_runtime.tools.code import CodeSandboxPlugin, CodeSandboxUnavailableError
from ai_runtime.tools.file import FileSandbox
from ai_runtime.tools.search import WebSearchPlugin
from ai_runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite


class DirectToolValidationRunner:
    """不经过模型，定位工具自身和安全边界是否正常。"""

    def __init__(
        self,
        config,
        *,
        search_plugin: WebSearchPlugin | None = None,
    ) -> None:
        self.config = config
        self.search_plugin = search_plugin or WebSearchPlugin.from_runtime_policy(
            getattr(config, "runtime_policy", {})
        )

    def run(self, *, include_network: bool = False) -> ValidationSuite:
        results = [
            self.verify_code_sandbox(),
            self.verify_file_sandbox(),
            self.verify_permission_boundary(),
            self.verify_skill_lifecycle(),
        ]
        results.append(
            self.verify_web_search()
            if include_network
            else CheckResult(
                check_id="tool.web_search",
                status=CheckStatus.SKIPPED,
                message="离线验证未启用真实网络搜索",
            )
        )
        return ValidationSuite("agent:direct-tools", tuple(results))

    def verify_code_sandbox(self) -> CheckResult:
        started = time.perf_counter()
        try:
            result = CodeSandboxPlugin(timeout_seconds=3).execute("print(6 * 7)")
            passed = result.get("stdout") == "42" and result.get("exit_code") == 0
            return CheckResult(
                check_id="tool.code_sandbox",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message="代码沙箱验证通过" if passed else "代码沙箱返回异常结果",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except CodeSandboxUnavailableError as exc:
            return CheckResult(
                check_id="tool.code_sandbox",
                status=CheckStatus.SKIPPED,
                message=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.code_sandbox", exc, started)

    def verify_file_sandbox(self) -> CheckResult:
        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="elfie-file-check-") as temp_dir:
                sandbox = FileSandbox(temp_dir)
                saved_name = sandbox.write_file("probe.txt", "runtime-ok")
                passed = (
                    saved_name == "probe.txt"
                    and sandbox.read_file("probe.txt") == "runtime-ok"
                    and "probe.txt" in sandbox.list_files()
                )
            return CheckResult(
                check_id="tool.local_file",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message="本地文件沙箱验证通过" if passed else "本地文件沙箱结果异常",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.local_file", exc, started)

    def verify_permission_boundary(self) -> CheckResult:
        started = time.perf_counter()
        manager = PermissionManager(self.config)
        try:
            manager.verify_action("CREATE_SKILL", "../escape.py")
        except PermissionDeniedError:
            return CheckResult(
                check_id="tool.permission_boundary",
                status=CheckStatus.PASSED,
                message="路径越界请求已被阻止",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.permission_boundary", exc, started)
        return CheckResult(
            check_id="tool.permission_boundary",
            status=CheckStatus.FAILED,
            message="路径越界请求未被阻止",
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    def verify_skill_lifecycle(self) -> CheckResult:
        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="elfie-skill-check-") as temp_dir:
                sandbox = FileSandbox(Path(temp_dir))
                plugin = SkillsSelfEvolutionPlugin(
                    PermissionManager(self.config),
                    file_sandbox=sandbox,
                )
                plugin.write_skill("probe", "print('skill-ok')")
                listed = plugin.list_skills()
                executed = plugin.run_skill("probe")
                passed = (
                    "probe.py" in listed
                    and executed.get("exit_code") == 0
                    and executed.get("stdout") == "skill-ok"
                )
            return CheckResult(
                check_id="tool.skill_lifecycle",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message="技能生命周期验证通过" if passed else "技能生命周期结果异常",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except CodeSandboxUnavailableError as exc:
            return CheckResult(
                check_id="tool.skill_lifecycle",
                status=CheckStatus.SKIPPED,
                message=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.skill_lifecycle", exc, started)

    def verify_web_search(self) -> CheckResult:
        started = time.perf_counter()
        try:
            result = self.search_plugin.search("ElfieNest runtime validation")
            passed = bool(str(result).strip())
            return CheckResult(
                check_id="tool.web_search",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message="网络搜索验证通过" if passed else "网络搜索返回空结果",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.web_search", exc, started)


def _failure(check_id: str, exc: Exception, started: float) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        status=CheckStatus.FAILED,
        message=str(exc),
        duration_ms=(time.perf_counter() - started) * 1000,
        details={"error_type": type(exc).__name__},
    )
