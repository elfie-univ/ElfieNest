from __future__ import annotations

import pytest
from pydantic import ValidationError

from elfie.brain import ToolPort, ToolRequest, ToolResult
from elfie.message_types import ErrorInfo


def test_tool_port_is_a_brain_owned_protocol_with_closed_models() -> None:
    assert getattr(ToolPort, "_is_protocol", False)
    assert ToolPort.__module__ == "elfie.brain.tool_port"
    assert ToolRequest.model_config["extra"] == "forbid"
    assert ToolResult.model_config["frozen"] is True


def test_tool_request_rejects_ambiguous_or_unscoped_operations() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(tool_key="web_search", operation="search")
    with pytest.raises(ValidationError):
        ToolRequest(
            tool_key="local_file",
            operation="read",
            resource_id="../outside.txt",
            query="unexpected",
        )
    with pytest.raises(ValidationError):
        ToolRequest(tool_key="local_file", operation="read")
    with pytest.raises(ValidationError):
        ToolRequest(
            tool_key="local_file",
            operation="read",
            resource_id="notes.txt",
        )


def test_tool_result_requires_typed_error_only_for_failures() -> None:
    success = ToolResult(tool_key="web_search", ok=True, content="facts")
    assert success.error is None

    with pytest.raises(ValidationError):
        ToolResult(tool_key="web_search", ok=False, content="denied")

    failure = ToolResult(
        tool_key="web_search",
        ok=False,
        content="denied",
        error=ErrorInfo(code="denied", message="denied"),
    )
    assert failure.error is not None
