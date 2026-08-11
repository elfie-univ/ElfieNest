"""Agent 的只读本地文件工具，只允许访问用户数据根目录。"""

from __future__ import annotations

from pathlib import Path

from infrastructure.persistence.data_home import get_runtime_dir


class LocalFileAccessError(RuntimeError):
    pass


class LocalFileAccessPlugin:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        max_read_bytes: int = 65536,
        max_items: int = 200,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else get_runtime_dir() / "unbound-elfie-workspace"
        )
        self.max_read_bytes = max_read_bytes
        self.max_items = max_items
        self.last_read_bytes = 0
        self.last_read_truncated = False
        self.last_list_items = 0
        self.last_list_truncated = False

    def read_text(self, relative_path: str) -> str:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise FileNotFoundError(f"本地文件不存在: {relative_path}")
        raw = target.read_bytes()
        self.last_read_bytes = len(raw)
        self.last_read_truncated = len(raw) > self.max_read_bytes
        if len(raw) > self.max_read_bytes:
            raw = raw[: self.max_read_bytes]
        return raw.decode("utf-8", errors="replace")

    def list_files(self, relative_path: str = ".") -> list[str]:
        target = self._resolve(relative_path)
        if not target.exists():
            return []
        if not target.is_dir():
            raise LocalFileAccessError(f"目标不是目录: {relative_path}")
        files = sorted(
            str(item.relative_to(self.root.resolve()))
            for item in target.iterdir()
            if item.is_file()
        )
        self.last_list_items = len(files)
        self.last_list_truncated = len(files) > self.max_items
        return files[: self.max_items]

    def _resolve(self, relative_path: str) -> Path:
        root = self.root.resolve()
        target = (root / relative_path).resolve()
        if target != root and root not in target.parents:
            raise LocalFileAccessError("本地文件访问越过了允许根目录")
        return target
