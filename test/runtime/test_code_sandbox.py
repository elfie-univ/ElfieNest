from __future__ import annotations

import pytest

from runtime.tools.code import CodeSandboxPlugin, CodeSandboxUnavailableError


def test_code_sandbox_does_not_execute_host_code_by_default() -> None:
    plugin = CodeSandboxPlugin()

    with pytest.raises(CodeSandboxUnavailableError, match="真实隔离"):
        plugin.execute("print(__import__('os').getcwd())")
