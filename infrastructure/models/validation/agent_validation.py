"""Tool invocation integration validation for the model adapter."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from infrastructure.models.inference.llm_api import call_llm_api
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.models.runtime_observations import get_runtime_observer
from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)
from infrastructure.tools.execution.loop import PortToolLoop
from infrastructure.tools.execution.permissions import PermissionManager
from infrastructure.tools.execution.skills_prompt import inject_skills_system_prompt
from infrastructure.tools.port_adapter import ToolPortAdapter
from infrastructure.tools.web_search.search import WebSearchPlugin

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
                observer = get_runtime_observer()
                policy = deepcopy(getattr(self.config, "runtime_policy", {}))
                tools = policy.setdefault("tools", {})
                tools.setdefault(tool_name, {})["enabled"] = True
                validation_config = SimpleNamespace(runtime_policy=policy)
                tool_port = ToolPortAdapter(
                    config=validation_config,
                    search_plugin=self.search_plugin,
                    permission_manager=PermissionManager(validation_config, observer),
                    observation_port=observer,
                    workspace_resolver=lambda scope_id: (
                        files_root if scope_id == "validation" else None
                    ),
                    allowed_tool_keys=(tool_name,),
                )
                loop = PortToolLoop(
                    tool_port,
                    allowed_tool_keys=(tool_name,),
                    scope_id="validation",
                )
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
