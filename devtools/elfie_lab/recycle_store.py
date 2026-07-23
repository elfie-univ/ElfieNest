"""Elfie Lab 可恢复删除存储。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple, Tuple


class InvalidRecycleIdError(ValueError):
    __slots__ = ("elfie_id",)

    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"无效的本地数据标识: {self.elfie_id}"


class RecycleSourceNotFoundError(FileNotFoundError):
    __slots__ = ("elfie_id",)

    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"测试精灵不存在: {self.elfie_id}"


class RecycleMoveError(OSError):
    __slots__ = ("cause", "elfie_id", "rollback_errors")

    def __init__(
        self,
        elfie_id: str,
        cause: str,
        rollback_errors: Tuple[str, ...] = (),
    ) -> None:
        super().__init__(elfie_id, cause, rollback_errors)
        self.elfie_id = elfie_id
        self.cause = cause
        self.rollback_errors = rollback_errors

    def __str__(self) -> str:
        detail = f"精灵删除失败，原数据已回滚: {self.elfie_id} ({self.cause})"
        if self.rollback_errors:
            return f"{detail}；回滚异常: {'; '.join(self.rollback_errors)}"
        return detail


class RecycleResult(NamedTuple):
    elfie_id: str
    bundle_dir: Path
    moved_sources: Tuple[str, ...]


class _RecycleManifest(NamedTuple):
    version: int
    deleted_elfie_id: str
    deleted_at: str
    moved_sources: Tuple[str, ...]


MovePath = Callable[[Path, Path], None]


class RecycleStore:
    """Move one Elfie's Lab data into a timestamped trash bundle."""

    def __init__(self, root: Path, move_path: MovePath | None = None) -> None:
        self.root = root
        self.trash_dir = root / "trash"
        self._move_path = move_path or self._rename

    def recycle(self, elfie_id: str) -> RecycleResult:
        self._validate_id(elfie_id)
        sources = self._sources(elfie_id)
        if not sources[0][1].is_dir():
            raise RecycleSourceNotFoundError(elfie_id)

        deleted_at = datetime.now(timezone.utc)
        bundle = (
            self.trash_dir / f"{deleted_at.strftime('%Y%m%dT%H%M%S%fZ')}-{elfie_id}"
        )
        moved_paths: list[tuple[Path, Path]] = []
        moved_sources: list[str] = []
        manifest_path = bundle / "manifest.json"
        try:
            bundle.mkdir(parents=True)
            for category, source in sources:
                if not source.exists():
                    continue
                destination = bundle / category / elfie_id
                destination.parent.mkdir(parents=True)
                self._move_path(source, destination)
                moved_paths.append((source, destination))
                moved_sources.append(f"{category}/{elfie_id}")

            manifest = _RecycleManifest(
                version=1,
                deleted_elfie_id=elfie_id,
                deleted_at=deleted_at.isoformat(),
                moved_sources=tuple(moved_sources),
            )
            manifest_path.write_text(
                json.dumps(manifest._asdict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            rollback_errors = self._rollback(bundle, manifest_path, moved_paths)
            raise RecycleMoveError(elfie_id, str(exc), rollback_errors) from exc
        return RecycleResult(elfie_id, bundle, tuple(moved_sources))

    def _rollback(
        self,
        bundle: Path,
        manifest_path: Path,
        moved_paths: list[tuple[Path, Path]],
    ) -> Tuple[str, ...]:
        rollback_errors = []
        for source, destination in reversed(moved_paths):
            try:
                self._move_path(destination, source)
            except OSError as exc:
                rollback_errors.append(f"{destination} -> {source}: {exc}")
        try:
            if manifest_path.exists():
                manifest_path.unlink()
            self._prune_empty_bundle(bundle)
        except OSError as exc:
            rollback_errors.append(f"清理空回收目录失败: {exc}")
        return tuple(rollback_errors)

    @staticmethod
    def _prune_empty_bundle(bundle: Path) -> None:
        for category in ("media", "sessions", "elfies"):
            category_dir = bundle / category
            if category_dir.is_dir() and not any(category_dir.iterdir()):
                category_dir.rmdir()
        if bundle.is_dir() and not any(bundle.iterdir()):
            bundle.rmdir()

    def _sources(self, elfie_id: str) -> Tuple[Tuple[str, Path], ...]:
        return (
            ("elfies", self.root / "elfies" / elfie_id),
            ("sessions", self.root / "sessions" / elfie_id),
            ("media", self.root / "media" / elfie_id),
        )

    @staticmethod
    def _rename(source: Path, destination: Path) -> None:
        source.rename(destination)

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not all(ch.isalnum() or ch in {"_", "-"} for ch in value):
            raise InvalidRecycleIdError(value)
