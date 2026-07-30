"""精灵稳定档案的 YAML 持久化。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

import yaml

from .models import ElfieProfile


class ElfieProfileRepository:
    """在精灵配置目录中原子读写 ``profile.yaml``。"""

    filename = "profile.yaml"

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
