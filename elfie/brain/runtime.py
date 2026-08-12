"""Lifecycle owner for one Elfie's private asynchronous Brain loop."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from elfie.brain.context_source import BrainContextState
from elfie.brain.coordinator import BrainCoordinator
from elfie.brain.cortical_worker import CorticalWorker
from elfie.brain.decision_decoder import DecisionPlanDecoder
from elfie.brain.decision_types import TurnDecision
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.output_ports import IntentExecutor
from elfie.brain.output_router import OutputRouter
from elfie.brain.output_types import ExecutionReceipt
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.reasoning import ReasoningRunResult
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.brain.turn_outcome import TurnOutcome
from elfie.message_types import ElfieId, TurnId, UTCDateTime


class BrainRuntime:
    """Own Brain coordinator, worker, decision boundary, and shutdown order."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: PerceptualWorkspace,
        emotion: EmotionSystem,
        homeostasis: HypothalamusEnergy,
        context: BrainContextState,
        clock: Callable[[], UTCDateTime],
        model_port: ModelPort,
        tool_port: ToolPort | None = None,
        skills: SkillManager,
        body_executor: IntentExecutor,
        message_executor: IntentExecutor,
        internal_executor: IntentExecutor,
    ) -> None:
        self._clock = clock
        self.context = context
        self.router = OutputRouter(
            elfie_id=elfie_id,
            capabilities=context,
            perception_sink=workspace,
            body_executor=body_executor,
            message_executor=message_executor,
            internal_executor=internal_executor,
            clock=clock,
        )
        worker = CorticalWorker(
            model_port=model_port,
            decoder=DecisionPlanDecoder(),
            tool_port=tool_port,
        )
        self.coordinator = BrainCoordinator(
            elfie_id=elfie_id,
            workspace=workspace,
            emotion=emotion,
            homeostasis=homeostasis,
            appraiser=LimbicAppraiser(),
            context_source=context,
            cortical_worker=worker,
            plan_sink=self.router,
            initial_timestamp=clock().timestamp(),
            allowed_tools=skills.allowed_tool_keys(),
        )
        self._started = False
        self._workspace = workspace

    def start(self) -> None:
        if self._started:
            return
        try:
            self.router.start()
            self.coordinator.start()
        except (OSError, RuntimeError):
            try:
                self.coordinator.stop()
            except RuntimeError:
                pass
            try:
                self.coordinator.join()
            except RuntimeError:
                pass
            try:
                self.router.stop()
            except RuntimeError:
                pass
            try:
                self.router.join()
            except RuntimeError:
                pass
            self._started = False
            raise
        self._started = True

    def post_clock(self, timestamp: float) -> None:
        self.coordinator.post_clock(BrainClockPulse(timestamp=timestamp))

    def notify_perception(self, *, urgent_reason: Optional[str] = None) -> None:
        self.coordinator.notify_perception(urgent_reason=urgent_reason)

    def outcomes(self) -> Tuple[TurnOutcome, ...]:
        return self.coordinator.outcomes()

    def wait_for_outcome_count(self, count: int, *, timeout: float) -> None:
        self.coordinator.wait_for_outcome_count(count, timeout=timeout)

    def wait_for_output(self, turn_id: TurnId, *, timeout: float) -> None:
        self.router.wait_for_turn(turn_id, timeout=timeout)

    def execution_receipts(self, turn_id: TurnId) -> Tuple[ExecutionReceipt, ...]:
        return self.router.receipts(turn_id)

    def decision(self, turn_id: TurnId) -> Optional[TurnDecision]:
        return self.router.decision(turn_id)

    def reasoning(self, turn_id: TurnId) -> Optional[ReasoningRunResult]:
        return self.coordinator.reasoning(turn_id)

    def stop(self) -> None:
        if not self._started:
            return
        self._workspace.stop()
        self.coordinator.stop()
        self.router.stop()

    def join(self) -> None:
        if not self._started:
            return
        self.coordinator.join()
        self.router.join()
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self.coordinator.is_alive


__all__ = ("BrainRuntime",)
