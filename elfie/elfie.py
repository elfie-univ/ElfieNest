"""Single-Elfie facade and lifecycle boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable

from elfie.body import BodyBinding, BodyRegistry
from elfie.body.contracts import BodySensorEvent
from elfie.body.port import BodyPort
from elfie.brain.decision_types import DecisionPlan
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.output_types import ExecutionReceipt
from elfie.brain.perception_types import IngestReceipt
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.brain.turn_outcome import TurnOutcome
from elfie.cognitive_runtime import ElfieCognitiveRuntime
from elfie.communication import CommunicationEnvelope, CommunicationHub
from elfie.communication.contracts import InboundDisposition, InboundDispositionStatus
from elfie.communication.perception_adapter import CommunicationPerceptionAdapter
from elfie.communication.router import RegisteredChannel
from elfie.initialization import assemble_anatomy
from elfie.lifecycle_errors import ElfieLifecycleError, InvalidClockDeltaError
from elfie.message_types import ElfieId, TurnId
from elfie.nervous_system import NervousSystem
from elfie.profile import ElfieProfile


class Elfie:
    """Own one complete Elfie's stable profile and asynchronous runtime."""

    def __init__(
        self,
        *,
        character_profile: ElfieProfile,
        memory_store: MemoryStorePort,
        body: BodyPort | None = None,
        communication: CommunicationHub | None = None,
        skills: SkillManager | None = None,
        model_port: ModelPort | None = None,
    ) -> None:
        character_profile.validate()
        self.character_profile = character_profile
        self.species_id = self.character_profile.identity.species_id
        self._elapsed_time = 0.0
        self._clock_lock = Lock()
        self.hypothalamus = HypothalamusEnergy(
            self.character_profile.system_limits,
            clock=lambda: self._elapsed_time,
        )
        self.amygdala = EmotionSystem(clock=lambda: self._elapsed_time)
        self.memory = MemorySystem(
            elfie_id=self.character_profile.identity.elfie_id,
            personality_data=self.character_profile.personality or None,
            storage=memory_store,
        )
        workspace_id = ElfieId(self.character_profile.identity.elfie_id)
        self.perceptual_workspace = PerceptualWorkspace(workspace_id)
        self.nervous_system = NervousSystem(
            self.character_profile.capabilities,
            perception_sink=self.perceptual_workspace,
            elfie_id=workspace_id,
            body_port=body,
        )
        self.anatomy_type, self.anatomy = assemble_anatomy(
            self.character_profile,
        )
        self.body_registry = BodyRegistry()
        self.body_binding = BodyBinding(self.body_registry)
        self.body_binding.attach(body)
        self.communication = communication or CommunicationHub(str(workspace_id))
        self.communication.bind_identity(str(workspace_id))
        self.skills = skills or SkillManager()
        self._cognitive_runtime: ElfieCognitiveRuntime | None = None
        if model_port is not None:
            self.configure_cognition(model_port)

    @property
    def profile(self) -> ElfieProfile:
        return self.character_profile

    @property
    def identity(self):
        return self.character_profile.identity

    @property
    def current_body(self) -> BodyPort | None:
        return self.body_binding.current

    @property
    def elapsed_time(self) -> float:
        with self._clock_lock:
            return self._elapsed_time

    @property
    def cognitive_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.elapsed_time, timezone.utc)

    @property
    def is_running(self) -> bool:
        runtime = self._cognitive_runtime
        return runtime is not None and runtime.is_running

    @property
    def cognition_configured(self) -> bool:
        return self._cognitive_runtime is not None

    def bind_identity(self, elfie_id: str) -> None:
        if self.cognition_configured and elfie_id != self.identity.elfie_id:
            raise ElfieLifecycleError(
                "cannot change Elfie identity after cognition assembly"
            )
        identity_changed = self.identity.elfie_id != elfie_id
        self.memory.bind_elfie_identity(elfie_id)
        if identity_changed:
            self.character_profile = replace(
                self.character_profile,
                identity=replace(self.identity, elfie_id=elfie_id),
            )
            self._reassemble_perception_identity(ElfieId(elfie_id))
        self.communication.bind_identity(elfie_id)

    def _reassemble_perception_identity(self, elfie_id: ElfieId) -> None:
        """Rebuild empty pre-cognition producers under the final identity."""
        self.perceptual_workspace = PerceptualWorkspace(elfie_id)
        self.nervous_system = NervousSystem(
            self.character_profile.capabilities,
            perception_sink=self.perceptual_workspace,
            elfie_id=elfie_id,
            body_port=self.current_body,
        )
        if self.communication.perception_adapter is not None:
            self.communication.bind_perception_adapter(
                CommunicationPerceptionAdapter(self.perceptual_workspace)
            )

    def register_body(self, body: BodyPort, *, make_current: bool = False) -> None:
        self.body_binding.register(body)
        if make_current:
            self.bind_body(body.body_id)

    def bind_body(self, body_id: str) -> BodyPort:
        current = self.body_binding.bind(body_id)
        self.nervous_system.bind_body_port(current)
        return current

    def unbind_body(self) -> BodyPort | None:
        previous = self.body_binding.unbind()
        self.nervous_system.bind_body_port(None)
        return previous

    def register_communication_channel(
        self,
        channel: RegisteredChannel,
        *,
        connect: bool = False,
        replace: bool = False,
    ) -> RegisteredChannel:
        return self.communication.register_channel(
            channel,
            connect=connect,
            replace=replace,
        )

    def configure_cognition(self, model_port: ModelPort) -> None:
        if self._cognitive_runtime is not None:
            raise ElfieLifecycleError("Elfie cognition is already configured")
        self.communication.bind_perception_adapter(
            CommunicationPerceptionAdapter(self.perceptual_workspace)
        )
        self._cognitive_runtime = ElfieCognitiveRuntime(
            elfie_id=ElfieId(self.identity.elfie_id),
            workspace=self.perceptual_workspace,
            emotion=self.amygdala,
            homeostasis=self.hypothalamus,
            memory=self.memory,
            nervous_system=self.nervous_system,
            communication=self.communication,
            current_body=lambda: self.current_body,
            clock=lambda: self.cognitive_datetime,
            model_port=model_port,
            skills=self.skills,
        )

    def start(self) -> None:
        self._require_cognitive_runtime().start()

    def stop(self) -> None:
        if self._cognitive_runtime is not None:
            self._cognitive_runtime.stop()

    def join(self) -> None:
        if self._cognitive_runtime is not None:
            self._cognitive_runtime.join()

    def advance_clock(self, seconds: float) -> None:
        if seconds < 0:
            raise InvalidClockDeltaError(seconds)
        with self._clock_lock:
            self._elapsed_time += seconds
            timestamp = self._elapsed_time
        self._require_cognitive_runtime().post_clock(timestamp)

    def pump_body_events(
        self,
        additional_events: Iterable[BodySensorEvent] = (),
    ) -> tuple[IngestReceipt, ...]:
        body = self.current_body
        events = list(body.read_sensor_events()) if body is not None else []
        events.extend(additional_events)
        previous_urgent_revision = self.nervous_system.urgent_revision
        receipts = self.nervous_system.receive_body_events(events)
        retries = self.nervous_system.retry_pending()
        communication_retries = self.communication.retry_perception()
        if events or retries or communication_retries:
            self._require_cognitive_runtime().notify_perception(
                urgent_reason=(
                    "body_reflex"
                    if self.nervous_system.urgent_revision > previous_urgent_revision
                    else None
                )
            )
        return receipts + retries + communication_retries

    def receive_communication_envelope(
        self,
        envelope: CommunicationEnvelope,
    ) -> InboundDisposition:
        disposition = self.communication.receive_envelope(envelope)
        if disposition.status is InboundDispositionStatus.ACCEPTED:
            self._require_cognitive_runtime().notify_perception()
        return disposition

    def turn_outcomes(self) -> tuple[TurnOutcome, ...]:
        return self._require_cognitive_runtime().outcomes()

    def wait_for_outcome_count(self, count: int, *, timeout: float) -> None:
        self._require_cognitive_runtime().wait_for_outcome_count(count, timeout=timeout)

    def wait_for_output(self, turn_id: TurnId, *, timeout: float) -> None:
        self._require_cognitive_runtime().wait_for_output(turn_id, timeout=timeout)

    def execution_receipts(self, turn_id: TurnId) -> tuple[ExecutionReceipt, ...]:
        return self._require_cognitive_runtime().execution_receipts(turn_id)

    def decision_plan(self, turn_id: TurnId) -> DecisionPlan | None:
        return self._require_cognitive_runtime().decision_plan(turn_id)

    def _require_cognitive_runtime(self) -> ElfieCognitiveRuntime:
        runtime = self._cognitive_runtime
        if runtime is None:
            raise ElfieLifecycleError("Elfie cognition is not configured")
        return runtime
