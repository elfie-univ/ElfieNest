"""Immutable state and budget contracts owned by the Energy system."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from elfie.message_types import FrozenContractModel, TurnId, UTCDateTime

_Percent = Annotated[float, Field(strict=True, ge=0.0, le=100.0)]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_PositiveBudget = Annotated[float, Field(strict=True, gt=0.0, le=100.0)]
_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]


class EnergySnapshot(FrozenContractModel):
    """Energy, fatigue and allocatable budgets at one simulation cutoff."""

    revision: _Revision
    captured_at: UTCDateTime
    energy: _Percent
    fatigue: _Percent
    sleeping: bool
    cognitive_mode: Literal["normal", "long", "degraded", "emergency"] = "normal"
    long_reasoning_allowed: bool = False
    available_cognitive_budget: _Percent = 0.0
    normal_budget_available: _Percent = 0.0
    emergency_reserve_available: _Percent = 0.0
    reserved_cognitive_budget: _Percent = 0.0


class CognitiveBudgetReservation(FrozenContractModel):
    """One deterministic per-Turn reservation issued before reasoning starts."""

    turn_id: TurnId
    mode: Literal["normal", "long", "degraded", "emergency"]
    source: Literal["normal", "emergency_reserve"]
    granted: _PositiveBudget
    owner_revision: _Revision
    purpose: _NonBlankText = "reasoning_turn"


__all__ = ("CognitiveBudgetReservation", "EnergySnapshot")
