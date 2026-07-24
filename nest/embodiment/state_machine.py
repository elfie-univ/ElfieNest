"""The sole persisted state vocabulary for an Elfie's Nest embodiment presence."""

from __future__ import annotations

from enum import Enum
from typing import Final, FrozenSet, Mapping


class EmbodimentTransitionError(ValueError):
    """Raised when a caller skips a required embodiment transition."""


class EmbodimentState(str, Enum):
    """Stable presence states; body objects and devices remain outside ``nest``."""

    AT_NEST = "at_nest"
    SWITCHING_TO_HOSTED = "switching_to_hosted"
    HOSTED = "hosted"
    RETURNING_TO_NEST = "returning_to_nest"
    OFFLINE = "offline"

    def transition_to(self, target: EmbodimentState) -> EmbodimentState:
        """Validate and return the next state without performing side effects."""
        if target not in _ALLOWED_TRANSITIONS[self]:
            raise EmbodimentTransitionError(
                f"不允许具身状态从 {self.value} 直接切换到 {target.value}"
            )
        return target


_ALLOWED_TRANSITIONS: Final[Mapping[EmbodimentState, FrozenSet[EmbodimentState]]] = {
    EmbodimentState.AT_NEST: frozenset(
        {EmbodimentState.SWITCHING_TO_HOSTED, EmbodimentState.OFFLINE}
    ),
    EmbodimentState.SWITCHING_TO_HOSTED: frozenset(
        {EmbodimentState.HOSTED, EmbodimentState.AT_NEST, EmbodimentState.OFFLINE}
    ),
    EmbodimentState.HOSTED: frozenset(
        {EmbodimentState.RETURNING_TO_NEST, EmbodimentState.OFFLINE}
    ),
    EmbodimentState.RETURNING_TO_NEST: frozenset(
        {EmbodimentState.AT_NEST, EmbodimentState.OFFLINE}
    ),
    EmbodimentState.OFFLINE: frozenset({EmbodimentState.AT_NEST}),
}
