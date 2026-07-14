"""测试精灵和调试会话的独立本地存储。"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from devtools.elfie_lab.schemas import ElfieSpec, new_id


class ElfieLabStorage:
    def __init__(self, data_dir: Optional[str] = None):
        configured = data_dir or os.getenv("ELFIE_LAB_DATA_DIR")
        self.root = Path(configured or "~/.elfienest/dev/elfie_lab").expanduser()
        self.elfies_dir = self.root / "elfies"
        self.sessions_dir = self.root / "sessions"
        self.elfies_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def list_elfies(self) -> List[ElfieSpec]:
        specs: List[ElfieSpec] = []
        for path in sorted(self.elfies_dir.glob("*/profile.json")):
            try:
                specs.append(ElfieSpec.from_dict(self._read_json(path)))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(specs, key=lambda item: item.updated_at, reverse=True)

    def create_elfie(
        self,
        name: str,
        anatomy_type: str = "biped",
        description: str = "",
    ) -> ElfieSpec:
        if anatomy_type not in {"biped", "quadruped"}:
            raise ValueError("身体形态只能是 biped 或 quadruped")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("精灵名称不能为空")
        spec = ElfieSpec(
            elfie_id=new_id("elfie"),
            name=clean_name,
            anatomy_type=anatomy_type,
            description=description.strip() or "用于本地调试的单精灵",
        )
        self._write_json(self.profile_path(spec.elfie_id), spec.to_dict())
        return spec

    def get_elfie(self, elfie_id: str) -> ElfieSpec:
        path = self.profile_path(elfie_id)
        if not path.exists():
            raise KeyError(f"测试精灵不存在: {elfie_id}")
        return ElfieSpec.from_dict(self._read_json(path))

    def profile_path(self, elfie_id: str) -> Path:
        self._validate_id(elfie_id)
        return self.elfies_dir / elfie_id / "profile.json"

    def memory_path(self, elfie_id: str) -> Path:
        self._validate_id(elfie_id)
        path = self.elfies_dir / elfie_id / "memory.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def session_path(self, elfie_id: str, session_id: str) -> Path:
        self._validate_id(elfie_id)
        self._validate_id(session_id)
        path = self.sessions_dir / elfie_id / f"{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def load_latest_session(self, elfie_id: str) -> Optional[Dict[str, Any]]:
        self._validate_id(elfie_id)
        directory = self.sessions_dir / elfie_id
        if not directory.exists():
            return None
        candidates = sorted(
            directory.glob("session_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return self._read_json(candidates[0]) if candidates else None

    def save_session(self, payload: Dict[str, Any]) -> None:
        self._write_json(
            self.session_path(str(payload["elfie_id"]), str(payload["session_id"])),
            payload,
        )

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not all(ch.isalnum() or ch in {"_", "-"} for ch in value):
            raise ValueError("无效的本地数据标识")

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"数据格式错误: {path}")
        return data

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
