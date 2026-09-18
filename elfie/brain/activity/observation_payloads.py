"""Named frozen payload models for activity-boundary observations.

The Activity Preflight owns one named payload carried inside a
``BrainObservation`` envelope (§A9). Every field is a raw value the
emitting code already holds at the emit point (P1 raw capture, no
inferred data).

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Tuple

from pydantic import Field

from elfie.message_types import FrozenContractModel


class ActivityPreflightVerdictObservation(FrozenContractModel):
    """One side-effect-free Activity Preflight verdict (§A9).

    ``status`` mirrors ``ActivityPreflightStatus``; ``reason_codes``
    carry the rejection/clarification evidence. ``evidence_issued`` is
    ``True`` exactly when a validated Preflight result was retained for
    the same-run commit boundary — the service never persists or touches
    an external system, which is the side-effect-free determination.
    """

    activity_id: str
    status: str
    reason_codes: Tuple[str, ...] = ()
    evidence_issued: bool = False
    step_count: int = Field(default=0, ge=0)
    estimated_budget: float = 0.0


__all__ = ("ActivityPreflightVerdictObservation",)
