"""精灵稳定档案的 YAML 持久化。"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from .models import ElfieProfile


class ElfieProfileRepository:
    """在精灵配置目录中原子读写 ``profile.yaml``。"""

    filename = "profile.yaml"
    legacy_sections = {
        "personality": "personality.yaml",
        "capabilities": "capabilities.yaml",
        "system_limits": "system_limits.yaml",
    }

    def __init__(self, config_dir: Union[str, Path]):
        self.config_dir = Path(config_dir).expanduser()
        self.path = self.config_dir / self.filename

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self, *, migrate_legacy: bool = True) -> ElfieProfile:
        if not self.exists():
            raise FileNotFoundError(f"精灵档案不存在: {self.path}")
        with self.path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"精灵档案根节点必须是映射: {self.path}")
        profile = ElfieProfile.from_dict(raw)
        if not migrate_legacy:
            return profile
        migrated = self.merge_legacy_sections(profile)
        if migrated != profile:
            self.save(migrated)
        return migrated

    def merge_legacy_sections(self, profile: ElfieProfile) -> ElfieProfile:
        """用旧三份 YAML 补齐老版本 profile.yaml 中缺失的稳定字段。"""
        updates: Dict[str, Dict[str, Any]] = {}
        for field_name, filename in self.legacy_sections.items():
            if getattr(profile, field_name):
                continue
            value = self._load_mapping(self.config_dir / filename)
            if value:
                updates[field_name] = value
        return replace(profile, **updates) if updates else profile

    def load_legacy_sections(self) -> Dict[str, Dict[str, Any]]:
        """读取迁移期配置；文件不存在或根节点不是映射时返回空映射。"""
        return {
            field_name: self._load_mapping(self.config_dir / filename)
            for field_name, filename in self.legacy_sections.items()
        }

    def save(self, profile: ElfieProfile) -> Path:
        profile.validate()
        self.config_dir.mkdir(parents=True, exist_ok=True)
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
