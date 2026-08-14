"""Infrastructure persistence for Brain creation seeds.

Profile storage deliberately contains only immutable identity and appearance.
Selfhood and Energy seeds are separate Brain-owned documents and are loaded by
Bootstrap before the Elfie aggregate is assembled.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import yaml


class _YamlBrainSeedAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, object]:
        if not self.exists():
            raise FileNotFoundError(f"Brain seed 不存在: {self.path}")
        with self.path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"Brain seed 根节点必须是映射: {self.path}")
        return dict(raw)

    def save(self, value: Mapping[str, object]) -> None:
        if not isinstance(value, Mapping):
            raise ValueError("Brain seed 必须是映射")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    dict(value),
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


class YamlSelfhoodSeedAdapter(_YamlBrainSeedAdapter):
    """Persist one Brain Selfhood creation seed."""

    filename = "selfhood.yaml"

    def __init__(self, brain_dir: str | Path) -> None:
        super().__init__(Path(brain_dir).expanduser() / self.filename)


class YamlEnergyLimitsAdapter(_YamlBrainSeedAdapter):
    """Persist one Brain Energy limits seed."""

    filename = "energy_limits.yaml"

    def __init__(self, brain_dir: str | Path) -> None:
        super().__init__(Path(brain_dir).expanduser() / self.filename)


__all__ = ("YamlEnergyLimitsAdapter", "YamlSelfhoodSeedAdapter")
