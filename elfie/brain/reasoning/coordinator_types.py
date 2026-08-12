"""Private mailbox and in-flight state for BrainCoordinator."""

from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event
from typing import Optional, Union

from typing_extensions import TypeAlias

from elfie.brain.emotion.appraiser import BrainClockPulse
from elfie.brain.reasoning.turn_outcome import TerminalStatus
from elfie.brain.reasoning.worker import ReasoningTask, ReasoningTurnResult
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import TurnId


# ``slots=True`` is unavailable under the repository's Python 3.9 contract.
@dataclass(frozen=True)
class PerceptionControl:
    urgent_reason: Optional[str]


@dataclass(frozen=True)
class WorkerDoneControl:
    turn_id: TurnId
    future: Future[ReasoningTurnResult]


@dataclass(frozen=True)
class BarrierControl:
    reached: Event


@dataclass(frozen=True)
class StopControl:
    pass


ControlMessage: TypeAlias = Union[
    BrainClockPulse,
    PerceptionControl,
    WorkerDoneControl,
    BarrierControl,
    StopControl,
]


# Mutable owner-thread state; intentionally not a frozen value contract.
@dataclass
class InFlightTurn:
    """Mutable turn state accessed only by the coordinator owner thread."""

    frame: TurnFrame
    task: ReasoningTask
    future: Future[ReasoningTurnResult]
    timeout_at: float
    terminal_status: Optional[TerminalStatus] = None
    terminal_reason: Optional[str] = None


__all__ = (
    "BarrierControl",
    "ControlMessage",
    "InFlightTurn",
    "PerceptionControl",
    "StopControl",
    "WorkerDoneControl",
)
