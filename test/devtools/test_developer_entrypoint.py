from __future__ import annotations

from pathlib import Path

from devtools.entrypoint import available_tools, resolve_tool


def test_developer_tools_are_explicit_and_do_not_include_user_service() -> None:
    # Given
    tools = available_tools()

    # When
    names = tuple(tool.name for tool in tools)

    # Then
    assert names == ("elfie-lab", "runtime-lab", "nest-lab")
    assert "serve" not in names


def test_nest_lab_resolution_uses_isolated_data_root(tmp_path: Path) -> None:
    # Given
    tool = resolve_tool("nest-lab", tmp_path)

    # When / Then
    assert tool.module == "devtools.nest_lab"
    assert tool.default_port == 8890
    assert tool.data_root == tmp_path / "nest_lab"
