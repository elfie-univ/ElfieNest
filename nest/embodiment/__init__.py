"""Nest-side embodiment presence semantics without body/network ownership."""

from .state_machine import EmbodimentState, EmbodimentTransitionError

__all__ = ["EmbodimentState", "EmbodimentTransitionError"]
