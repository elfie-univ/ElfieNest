"""Packaged immutable Energy limits owned by Brain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_packaged_energy_limits() -> dict[str, Any]:
    """Load the creation-time homeostasis limits bundled with Brain."""
    path = Path(__file__).with_name("defaults.yaml")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"默认 Energy limits 必须是映射: {path}")
    return dict(raw)


__all__ = ("load_packaged_energy_limits",)
