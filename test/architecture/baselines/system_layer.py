"""Exact temporary baseline for known system architecture violations.

Entries may be removed by an approved migration but never added to make a new
dependency or technical import pass.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

LEGACY_SYSTEM_LAYER_VIOLATIONS: Dict[str, FrozenSet[str]] = {
    "elfie_forbidden_module_imports": frozenset(),
    "elfie_technical_imports": frozenset(),
    "nest_forbidden_module_imports": frozenset(),
    "nest_technical_imports": frozenset(),
}
