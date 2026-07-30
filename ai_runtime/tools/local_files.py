"""Agent 的只读本地文件工具，只允许访问用户数据根目录。"""

from __future__ import annotations

from pathlib import Path


class LocalFileAccessError(RuntimeError):
    pass


class LocalFileAccessPlugin:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def read_text(self, relative_path: str) -> str:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise FileNotFoundError(f"本地文件不存在: {relative_path}")
        return target.read_text(encoding="utf-8")

    def list_files(self, relative_path: str = ".") -> list[str]:
        target = self._resolve(relative_path)
        if not target.exists():
            return []
        if not target.is_dir():
            raise LocalFileAccessError(f"目标不是目录: {relative_path}")
        return sorted(
            str(item.relative_to(self.root.resolve()))
            for item in target.iterdir()
            if item.is_file()
        )

    def _resolve(self, relative_path: str) -> Path:
        root = self.root.resolve()
        target = (root / relative_path).resolve()
        if target != root and root not in target.parents:
            raise LocalFileAccessError("本地文件访问越过了允许根目录")
        return target
