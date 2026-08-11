"""Immutable profile defaults shipped with the Elfie package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_SECTION_FILES = {
    "personality": "personality.yaml",
    "capabilities": "capabilities.yaml",
    "system_limits": "system_limits.yaml",
}


def load_packaged_profile_defaults() -> dict[str, dict[str, Any]]:
    """Read the immutable defaults bundled with the profile domain."""
    defaults_dir = Path(__file__).with_name("defaults")
    sections: dict[str, dict[str, Any]] = {}
    for field_name, filename in _DEFAULT_SECTION_FILES.items():
        path = defaults_dir / filename
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"默认精灵配置必须是映射: {path}")
        sections[field_name] = dict(raw)
    return sections


__all__ = ["load_packaged_profile_defaults"]
