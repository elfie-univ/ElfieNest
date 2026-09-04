"""Brain-owned authorization for semantic Tool capabilities.

Tool authorization is deliberately separate from Agent Skills.  A Skill is a
loadable procedure; this policy only decides which already-registered Tools a
ReasoningRun may request.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

_DEFAULT_TOOL_KEYS: Tuple[str, ...] = ("web_search", "local_file")


@dataclass(frozen=True)
class ToolPolicy:
    """Allow a bounded set of Tool names and apply explicit denials."""

    configured_tool_keys: Tuple[str, ...] = _DEFAULT_TOOL_KEYS
    denied_tool_keys: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        normalized = tuple(
            dict.fromkeys(str(key).strip() for key in self.configured_tool_keys)
        )
        if any(not key for key in normalized):
            raise ValueError("configured_tool_keys must not contain blanks")
        if len(normalized) != len(self.configured_tool_keys):
            object.__setattr__(self, "configured_tool_keys", normalized)

    def allowed_tool_keys(self) -> Tuple[str, ...]:
        """Return configured Tool names after policy denials."""
        return tuple(
            key for key in self.configured_tool_keys if key not in self.denied_tool_keys
        )

    def authorize(
        self, requested_tool_keys: Optional[Iterable[str]]
    ) -> Tuple[str, ...]:
        """Intersect a Run request with this Brain-owned policy."""
        if requested_tool_keys is None:
            return ()
        allowed = set(self.allowed_tool_keys())
        result: list[str] = []
        for raw_key in requested_tool_keys:
            key = str(raw_key).strip()
            if key in allowed and key not in result:
                result.append(key)
        return tuple(result)


__all__ = ("ToolPolicy",)
