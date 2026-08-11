"""Direct validation for the two phase-one safe tools."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Protocol

from infrastructure.models.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)
from infrastructure.tools.local_files import LocalFileAccessPlugin
from infrastructure.tools.search import WebSearchPlugin


class SearchPlugin(Protocol):
    def search(self, query: str) -> str: ...


class DirectToolValidationRunner:
    def __init__(
        self,
        config: object,
        *,
        search_plugin: SearchPlugin | None = None,
    ) -> None:
        self.config = config
        self.search_plugin = search_plugin or WebSearchPlugin.from_runtime_policy(
            getattr(config, "runtime_policy", {})
        )

    def run(self, *, include_network: bool = False) -> ValidationSuite:
        results = [self.verify_file_sandbox()]
        results.append(
            self.verify_web_search()
            if include_network
            else CheckResult(
                check_id="tool.web_search",
                status=CheckStatus.SKIPPED,
                message="Offline validation: real web search not enabled",
            )
        )
        return ValidationSuite("agent:direct-tools", tuple(results))

    def verify_file_sandbox(self) -> CheckResult:
        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="elfie-file-check-") as temp_dir:
                root = Path(temp_dir)
                (root / "probe.txt").write_text("runtime-ok", encoding="utf-8")
                sandbox = LocalFileAccessPlugin(root)
                passed = (
                    sandbox.read_text("probe.txt") == "runtime-ok"
                    and "probe.txt" in sandbox.list_files()
                )
            return CheckResult(
                check_id="tool.local_file",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message=(
                    "Read-only local file validation passed"
                    if passed
                    else "Read-only local file validation failed"
                ),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return _failure("tool.local_file", exc, started)

    def verify_web_search(self) -> CheckResult:
        started = time.perf_counter()
        try:
            result = self.search_plugin.search("ElfieNest runtime validation")
            passed = bool(str(result).strip())
            return CheckResult(
                check_id="tool.web_search",
                status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
                message=(
                    "Web search validation passed"
                    if passed
                    else "Web search returned empty results"
                ),
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
