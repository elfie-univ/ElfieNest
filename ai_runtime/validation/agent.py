"""Tool invocation integration validation after connecting model to Runtime Agent."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.gateway.llm_api import call_llm_api
from ai_runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext
from ai_runtime.gateway.skills_prompt import inject_skills_system_prompt
from ai_runtime.safety.permissions import PermissionManager
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite
from infrastructure.tools.local_files import LocalFileAccessPlugin
from infrastructure.tools.search import WebSearchPlugin

AgentModelCaller = Callable[
    [str, str, list[dict[str, Any]], float, int],
    str,
]


class ModelAgentValidationRunner:
    def __init__(
        self,
        config: LLMRuntimeConfig,
        *,
        model_caller: AgentModelCaller | None = None,
        search_plugin: Any = None,
    ) -> None:
        self.config = config
        self.model_caller = model_caller or self._call_model
        self.search_plugin = search_plugin or WebSearchPlugin()

    def verify(
        self,
        provider: str,
        model: str,
        tools: Sequence[str] = ("local_file",),
    ) -> ValidationSuite:
        return ValidationSuite(
            name=f"agent:{provider}/{model}",
            results=tuple(
                self.verify_tool(provider, model, tool_name) for tool_name in tools
            ),
        )

    def verify_tool(self, provider: str, model: str, tool_name: str) -> CheckResult:
        if tool_name not in {"local_file", "web_search"}:
            return CheckResult(
                check_id=f"agent.{provider}.{model}.{tool_name}",
                status=CheckStatus.SKIPPED,
                message="Model integration scenario not defined for this tool",
                provider=provider,
                model=model,
            )

        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="elfie-agent-check-") as temp_dir:
                root = Path(temp_dir)
                files_root = root / "files"
                files_root.mkdir()
                (files_root / "probe.txt").write_text(
                    "ELFIE_LOCAL_FILE_OK", encoding="utf-8"
                )
                permission = PermissionManager(self.config)
                context = ToolLoopContext(
                    allowed_skills=(tool_name,),
                    search_plugin=self.search_plugin,
                    permission_manager=permission,
                    file_access_plugin=LocalFileAccessPlugin(files_root),
                )
                loop = RuntimeToolLoop(context)
                messages: list[dict[str, Any]] = [
                    {"role": "user", "content": _tool_probe_prompt(tool_name)}
                ]
                inject_skills_system_prompt(messages, [tool_name])

                def invoke(loop_messages: list[dict[str, Any]]) -> str:
                    return self.model_caller(
                        provider,
                        model,
                        loop_messages,
                        0.0,
                        256,
                    )

                final_text = loop.run(messages, 2, invoke)
                tool_called = len(messages) >= 3
                passed = tool_called and bool(str(final_text).strip())
                return CheckResult(
                    check_id=f"agent.{provider}.{model}.{tool_name}",
                    status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                    message=(
                        "Model Agent tool invocation passed"
                        if passed
                        else "Model did not invoke tool per protocol"
                    ),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    provider=provider,
                    model=model,
                    details={"tool_called": tool_called},
                )
        except Exception as exc:
            return CheckResult(
                check_id=f"agent.{provider}.{model}.{tool_name}",
                status=CheckStatus.FAILED,
                message=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
                provider=provider,
                model=model,
                details={"error_type": type(exc).__name__},
            )

    def _call_model(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        return call_llm_api(
            self.config,
            provider,
            model,
            messages,
            temperature,
            max_tokens,
        )


def _tool_probe_prompt(tool_name: str) -> str:
    if tool_name == "local_file":
        return "请必须读取本地文件 probe.txt，并根据文件内容回答。"
    return "请必须使用联网搜索工具搜索 ElfieNest，并根据搜索结果回答。"
