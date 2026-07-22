"""Private mailbox and in-flight state for BrainCoordinator."""

from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event
from typing import Optional, Union

from typing_extensions import TypeAlias

from elfie.brain.cortical_worker import CorticalTask, CorticalTurnResult
from elfie.brain.limbic_appraiser import BrainClockPulse
from elfie.brain.perception_types import PerceptionFrame
from elfie.brain.turn_outcome import TerminalStatus
from elfie.message_types import TurnId


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class PerceptionControl:
    urgent_reason: Optional[str]


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class WorkerDoneControl:
    turn_id: TurnId
    future: Future[CorticalTurnResult]


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class BarrierControl:
    reached: Event


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class StopControl:
    pass


ControlMessage: TypeAlias = Union[
    BrainClockPulse,
    PerceptionControl,
    WorkerDoneControl,
    BarrierControl,
    StopControl,
]


@dataclass  # noqa: MUTABLE_OK  # noqa: SLOTS_OK - owner state on Python 3.9
class InFlightTurn:
    """Mutable turn state accessed only by the coordinator owner thread."""

    frame: PerceptionFrame
    task: CorticalTask
    future: Future[CorticalTurnResult]
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
