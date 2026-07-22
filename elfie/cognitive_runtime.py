"""Lifecycle assembly for one Elfie's asynchronous cognitive loop."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from elfie.body.port import BodyPort
from elfie.brain.coordinator import BrainCoordinator
from elfie.brain.cortical_worker import CorticalWorker
from elfie.brain.decision_decoder import DecisionPlanDecoder
from elfie.brain.decision_types import DecisionPlan, InternalIntent
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.internal_output import InternalIntentExecutor
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.memory import MemorySystem
from elfie.brain.output_router import OutputRouter
from elfie.brain.output_types import ExecutionReceipt, IntentExecutionResult
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.runtime_port import CorticalRuntimePort
from elfie.brain.turn_outcome import TurnOutcome
from elfie.cognitive_context import ElfieContextSource
from elfie.communication import CommunicationHub
from elfie.communication.output_executor import CommunicationIntentExecutor
from elfie.message_types import ElfieId, TurnId, UTCDateTime
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor
from elfie.skills import SkillManager


class DefaultInternalIntentSink:
    """Acknowledge closed internal intents until richer memory work is enabled."""

    def execute(
        self,
        plan: DecisionPlan,
        intent: InternalIntent,
    ) -> IntentExecutionResult:
        del plan, intent
        return IntentExecutionResult.completed()


class ElfieCognitiveRuntime:
    """Own Coordinator, cortical worker, OutputRouter, and their shutdown order."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: PerceptualWorkspace,
        emotion: EmotionSystem,
        homeostasis: HypothalamusEnergy,
        memory: MemorySystem,
        nervous_system: NervousSystem,
        communication: CommunicationHub,
        current_body: Callable[[], Optional[BodyPort]],
        clock: Callable[[], UTCDateTime],
        cortical_runtime: CorticalRuntimePort,
        skills: SkillManager,
    ) -> None:
        self._clock = clock
        self.context_source = ElfieContextSource(
            memory=memory,
            current_body=current_body,
            communication=communication,
            clock=clock,
        )
        body_executor = NervousSystemIntentExecutor(
            nervous_system=nervous_system,
            current_body=current_body,
            clock=clock,
        )
        message_executor = CommunicationIntentExecutor(
            hub=communication,
            elfie_id=elfie_id,
            capabilities=self.context_source,
            clock=clock,
        )
        internal_executor = InternalIntentExecutor(DefaultInternalIntentSink())
        self.router = OutputRouter(
            elfie_id=elfie_id,
            capabilities=self.context_source,
            perception_sink=workspace,
            body_executor=body_executor,
            message_executor=message_executor,
            internal_executor=internal_executor,
            clock=clock,
        )
        worker = CorticalWorker(
            runtime=cortical_runtime,
            decoder=DecisionPlanDecoder(),
        )
        self.coordinator = BrainCoordinator(
            elfie_id=elfie_id,
            workspace=workspace,
            emotion=emotion,
            homeostasis=homeostasis,
            appraiser=LimbicAppraiser(),
            context_source=self.context_source,
            cortical_worker=worker,
            plan_sink=self.router,
            initial_timestamp=clock().timestamp(),
            allowed_tools=skills.allowed_runtime_tools(),
        )
        self._started = False
        self._workspace = workspace
        self._nervous_system = nervous_system
        self._communication = communication

    def start(self) -> None:
        if self._started:
            return
        self.router.start()
        self.coordinator.start()
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

    def stop(self) -> None:
        if not self._started:
            return
        self._workspace.stop()
        self._communication.close()
        self._nervous_system.close_perception()
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


__all__ = ("DefaultInternalIntentSink", "ElfieCognitiveRuntime")
