"""精灵稳定档案的 YAML 持久化。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from .models import ElfieProfile


class ElfieProfileRepository:
    """在精灵配置目录中原子读写 ``profile.yaml``。"""

    filename = "profile.yaml"
    default_sections = {
        "personality": "personality.yaml",
        "capabilities": "capabilities.yaml",
        "system_limits": "system_limits.yaml",
    }

    def __init__(self, config_dir: Union[str, Path]):
        self.config_dir = Path(config_dir).expanduser()
        self.path = self.config_dir / self.filename

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> ElfieProfile:
        if not self.exists():
            raise FileNotFoundError(f"精灵档案不存在: {self.path}")
        with self.path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"精灵档案根节点必须是映射: {self.path}")
        return ElfieProfile.from_dict(raw)

    def load_default_sections(self) -> Dict[str, Dict[str, Any]]:
        """Read bundled profile sections without requiring a canonical profile."""
        return {
            field_name: self._load_mapping(self.config_dir / filename)
            for field_name, filename in self.default_sections.items()
        }

    def save(self, profile: ElfieProfile) -> Path:
        profile.validate()
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.config_dir, 0o700)
        temporary = self.path.with_suffix(".yaml.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    profile.to_dict(),
                    handle,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                os.chmod(self.path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()
        return self.path

    @staticmethod
    def _load_mapping(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError):
            return {}
        return dict(raw) if isinstance(raw, dict) else {}
