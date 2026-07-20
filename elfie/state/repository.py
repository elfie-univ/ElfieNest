"""精灵动态状态的 YAML 持久化。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

import yaml

from .models import ElfieState


class ElfieStateRepository:
    """在精灵目录中原子读写 state.yaml。"""

    filename = "state.yaml"

    def __init__(self, config_dir: Union[str, Path]):
        self.config_dir = Path(config_dir).expanduser()
        self.path = self.config_dir / self.filename

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> ElfieState:
        if not self.exists():
            raise FileNotFoundError(f"精灵状态不存在: {self.path}")
        with self.path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"精灵状态根节点必须是映射: {self.path}")
        return ElfieState.from_dict(raw)

    def save(self, state: ElfieState) -> Path:
        state.validate()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".yaml.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    state.to_dict(),
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
