from __future__ import annotations

import pytest

from ai_runtime.tools.code import CodeSandboxPlugin, CodeSandboxUnavailableError


def test_code_sandbox_does_not_execute_host_code_by_default() -> None:
    plugin = CodeSandboxPlugin()

    with pytest.raises(CodeSandboxUnavailableError, match="no real isolated sandbox"):
        plugin.execute("print(__import__('os').getcwd())")
