"""Developer Tool 的工具目录与解析规则。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

from runtime.storage.data_home import get_elfie_home


@dataclass(frozen=True)
class DeveloperTool:
    """一个开发者工具的稳定启动契约。"""

    name: str
    module: str
    default_port: int | None
    data_root: Path


class UnknownDeveloperToolError(ValueError):
    """请求了不存在的开发者工具。"""


_TOOL_NAMES: Final[tuple[tuple[str, str, int | None, str], ...]] = (
    ("elfie-lab", "devtools.elfie_lab", 8877, "elfie_lab"),
    ("runtime-lab", "devtools.runtime_lab", None, "runtime_lab"),
    ("nest-lab", "devtools.nest_lab", 8890, "nest_lab"),
)


def available_tools(data_root: Path | None = None) -> tuple[DeveloperTool, ...]:
    """返回 Developer Tool 的固定顺序目录。"""
    root = (data_root or get_elfie_home() / "developer").resolve()
    return tuple(
        DeveloperTool(name, module, port, root / directory)
        for name, module, port, directory in _TOOL_NAMES
    )


def resolve_tool(name: str, data_root: Path | None = None) -> DeveloperTool:
    """按命令名解析工具，未知名称以明确异常返回。"""
    for tool in available_tools(data_root):
        if tool.name == name:
            return tool
    raise UnknownDeveloperToolError(f"未知 Developer Tool: {name}")


def tool_names(tools: Iterable[DeveloperTool] | None = None) -> tuple[str, ...]:
    """返回用于 CLI choices 和菜单展示的工具名。"""
    return tuple(tool.name for tool in (tools or available_tools()))
