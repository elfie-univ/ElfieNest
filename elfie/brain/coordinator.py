"""Single-owner Brain loop with a non-blocking cortical worker."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Event
from typing import Optional, Tuple
from uuid import uuid4

from elfie.brain.coordinator_completion import CoordinatorCompletionHandler
from elfie.brain.coordinator_outcomes import (
    cortical_failure_outcome,
    cortical_timeout_outcome,
)
from elfie.brain.coordinator_ports import BrainContextSource, DecisionPlanSink
from elfie.brain.coordinator_runtime import CoordinatorRuntime, TurnOutcomeBuffer
from elfie.brain.coordinator_turn import CoordinatorTurnFactory
from elfie.brain.coordinator_types import (
    BarrierControl,
    InFlightTurn,
    PerceptionControl,
    StopControl,
    WorkerDoneControl,
)
from elfie.brain.cortical_worker import CorticalExecutionPort
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.turn_outcome import TerminalStatus, TurnOutcome
from elfie.brain.turn_trigger_policy import TurnTriggerPolicy
from elfie.message_types import ElfieId, TurnId


class BrainCoordinator:
    """Own Brain mutation, frame claims, and one in-flight cortical turn."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: PerceptualWorkspace,
        emotion: EmotionSystem,
        homeostasis: HypothalamusEnergy,
        appraiser: LimbicAppraiser,
        context_source: BrainContextSource,
        cortical_worker: CorticalExecutionPort,
        plan_sink: DecisionPlanSink,
        initial_timestamp: float,
        next_autonomous_at: Optional[float] = None,
        hard_timeout_seconds: float = 45.0,
        trigger_policy: Optional[TurnTriggerPolicy] = None,
        allowed_tools: Tuple[str, ...] = (),
    ) -> None:
        self._elfie_id = elfie_id
        self._workspace = workspace
        self._emotion = emotion
        self._homeostasis = homeostasis
        self._appraiser = appraiser
        self._context_source = context_source
        self._worker = cortical_worker
        self._plan_sink = plan_sink
        self._timestamp = initial_timestamp
        self._next_autonomous_at = next_autonomous_at
        self._hard_timeout = hard_timeout_seconds
        self._policy = trigger_policy or TurnTriggerPolicy()
        self._turn_factory = CoordinatorTurnFactory(
            emotion=emotion,
            homeostasis=homeostasis,
            appraiser=appraiser,
            context_source=context_source,
            hard_timeout_seconds=hard_timeout_seconds,
            allowed_tools=allowed_tools,
        )
        self._runtime = CoordinatorRuntime(elfie_id, cortical_worker)
        self._inflight: Optional[InFlightTurn] = None
        self._outcomes = TurnOutcomeBuffer()
        self._completion = CoordinatorCompletionHandler(
            workspace=workspace,
            plan_sink=plan_sink,
            outcomes=self._outcomes,
        )

    def start(self) -> None:
        """Start worker and owner thread; repeated calls are idempotent."""
        self._runtime.start(self._run)

    def post_clock(self, pulse: BrainClockPulse) -> None:
        self._runtime.post(pulse)

    def notify_perception(self, *, urgent_reason: Optional[str] = None) -> None:
        self._runtime.post(PerceptionControl(urgent_reason))

    def synchronize(self, timeout: float = 1.0) -> None:
        """Wait until all mailbox messages posted before this call are handled."""
        reached = Event()
        self._runtime.post(BarrierControl(reached))
        if not reached.wait(timeout):
            raise TimeoutError("brain coordinator synchronization timed out")

    def stop(self) -> None:
        """Request explicit shutdown once and stop accepting cortical work."""
        self._runtime.stop()

    def join(self) -> None:
        """Join both owner and cortical threads; repeated calls are safe."""
        self._runtime.join()

    @property
    def is_alive(self) -> bool:
        return self._runtime.is_alive

    def outcomes(self) -> Tuple[TurnOutcome, ...]:
        return self._outcomes.snapshot()

    def wait_for_outcome(self, timeout: float = 1.0) -> None:
        self._outcomes.wait(timeout)

    def wait_for_outcome_count(self, count: int, *, timeout: float = 1.0) -> None:
        """Wait for a deterministic number of terminal cognitive turns."""
        self._outcomes.wait_for_count(count, timeout)

    def _run(self) -> None:
        while True:
            message = self._runtime.receive()
            if isinstance(message, StopControl):
                self._cancel_on_stop()
                return
            if isinstance(message, BrainClockPulse):  # noqa: IF_VARIANT_OK - Python 3.9
                self._handle_clock(message)
            elif isinstance(message, PerceptionControl):  # noqa: IF_VARIANT_OK - Python 3.9
                if message.urgent_reason is not None and self._inflight is not None:
                    self._mark_stale(self._inflight, message.urgent_reason)
                self._maybe_start_turn()
            elif isinstance(message, WorkerDoneControl):  # noqa: IF_VARIANT_OK - Python 3.9
                self._handle_worker_done(message)
            elif isinstance(message, BarrierControl):
                message.reached.set()

    def _handle_clock(self, pulse: BrainClockPulse) -> None:
        self._emotion.advance_to(pulse.timestamp)
        self._homeostasis.advance_to(pulse.timestamp)
        self._timestamp = pulse.timestamp
        if (
            self._inflight is not None
            and self._inflight.terminal_status is None
            and pulse.timestamp >= self._inflight.timeout_at
        ):
            self._timeout_turn(self._inflight)
        self._maybe_start_turn()

    def _maybe_start_turn(self) -> None:
        if self._inflight is not None:
            return
        autonomous_due = self._ensure_autonomous_event()
        metrics = self._workspace.metrics()
        now = datetime.fromtimestamp(self._timestamp, timezone.utc)
        decision = self._policy.evaluate(
            metrics,
            now=now,
            autonomous_due=autonomous_due,
        )
        if decision.reason is None or decision.cutoff_seq is None:
            return
        turn_id = TurnId(f"turn_{uuid4().hex}")
        frame = self._workspace.claim_frame(
            decision.cutoff_seq,
            turn_id=turn_id,
            reason=decision.reason,
            captured_at=now,
        )
        try:
            task = self._turn_factory.build_task(frame, turn_id, self._timestamp)
            future = self._worker.submit(task)
        except Exception as error:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - claim boundary
            self._workspace.release(frame.frame_id, turn_id, type(error).__name__)
            self._outcomes.record(
                cortical_failure_outcome(
                    turn_id=turn_id,
                    frame_id=frame.frame_id,
                    error_code=type(error).__name__,
                )
            )
            return
        inflight = InFlightTurn(
            frame=frame,
            task=task,
            future=future,
            timeout_at=self._timestamp + self._hard_timeout,
        )
        self._inflight = inflight
        future.add_done_callback(
            lambda completed: self._runtime.post(WorkerDoneControl(turn_id, completed))
        )

    def _handle_worker_done(self, control: WorkerDoneControl) -> None:
        inflight = self._inflight
        if inflight is None or control.turn_id != inflight.task.seed.turn_id:
            return
        self._completion.complete(inflight, control)
        self._inflight = None

    def _mark_stale(self, inflight: InFlightTurn, reason: str) -> None:
        if inflight.terminal_status is not None:
            return
        inflight.terminal_status = TerminalStatus.STALE
        inflight.terminal_reason = reason
        self._plan_sink.cancel_stale(inflight.task.seed.turn_id, reason)

    def _timeout_turn(self, inflight: InFlightTurn) -> None:
        self._worker.abandon(inflight.future)
        plan = self._turn_factory.noop_plan(
            inflight.task.seed,
            "cortical_hard_timeout",
        )
        if self._plan_sink.accept(plan):
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._outcomes.record(cortical_timeout_outcome(plan))
            inflight.terminal_status = TerminalStatus.TIMED_OUT
            inflight.terminal_reason = "cortical_hard_timeout"
        else:
            self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                "router_rejected_timeout",
            )
            self._outcomes.record(
                cortical_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code="router_rejected_timeout",
                )
            )
        self._inflight = None

    def _ensure_autonomous_event(self) -> bool:
        if self._next_autonomous_at is None or self._timestamp < self._next_autonomous_at:
            return False
        self._workspace.publish(
            self._turn_factory.autonomous_event(self._elfie_id, self._timestamp)
        )
        self._next_autonomous_at = None
        return True

    def _cancel_on_stop(self) -> None:
        inflight = self._inflight
        if inflight is None:
            return
        self._worker.abandon(inflight.future)
        if inflight.terminal_status is not None:
            self._inflight = None
            return
        self._plan_sink.cancel_stale(inflight.task.seed.turn_id, "coordinator_stopped")
        self._workspace.release(
            inflight.frame.frame_id,
            inflight.task.seed.turn_id,
            "coordinator_stopped",
        )
        self._inflight = None

__all__ = ("BrainCoordinator",)
