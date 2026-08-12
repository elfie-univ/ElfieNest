"""Single-Elfie facade and lifecycle boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable

from elfie.body import BodyBinding, BodyRegistry
from elfie.body.contracts import BodySensorEvent
from elfie.body.port import BodyPort
from elfie.brain.activity import ActivityStorePort, InMemoryActivityStore
from elfie.brain.context_types import (
    OrientationSnapshot,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.decision_types import TurnDecision
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.output_types import ExecutionReceipt
from elfie.brain.perception_types import IngestReceipt
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.reasoning import ReasoningRunResult
from elfie.brain.runtime import BrainRuntime
from elfie.brain.runtime_port import ModelPort
from elfie.brain.selfhood import SelfhoodSystem
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.brain.turn_outcome import TurnOutcome
from elfie.brain_wiring import assemble_brain_runtime
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
        tool_port: ToolPort | None = None,
        activity_store: ActivityStorePort | None = None,
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
        self.selfhood = SelfhoodSystem.from_personality_data(
            self.character_profile.personality,
            initial_at=self.cognitive_datetime,
            profile_revision=self.character_profile.schema_version,
        )
        self.amygdala = EmotionSystem(
            personality=self.selfhood.big_five_dict(),
            clock=lambda: self._elapsed_time,
        )
        self.memory = MemorySystem(
            elfie_id=self.character_profile.identity.elfie_id,
            personality_data=self.selfhood.seed_data(
                display_name=self.character_profile.identity.display_name
            ),
            storage=memory_store,
            clock=lambda: self.cognitive_datetime,
            initial_at=self.cognitive_datetime,
        )
        self.activity_store = activity_store or InMemoryActivityStore()
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
        self.nervous_system.bind_body_port(
            body,
            body_generation=self.body_binding.current_generation,
        )
        self.communication = communication or CommunicationHub(str(workspace_id))
        self.communication.bind_identity(str(workspace_id))
        self.skills = skills or SkillManager()
        self._brain_runtime: BrainRuntime | None = None
        if model_port is not None:
            self.configure_cognition(model_port, tool_port=tool_port)

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
    def current_body_generation(self) -> int | None:
        """Authority generation for the currently selected Body, if any."""
        return self.body_binding.current_generation

    @property
    def elapsed_time(self) -> float:
        with self._clock_lock:
            return self._elapsed_time

    @property
    def cognitive_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.elapsed_time, timezone.utc)

    @property
    def is_running(self) -> bool:
        runtime = self._brain_runtime
        return runtime is not None and runtime.is_running

    @property
    def cognition_configured(self) -> bool:
        return self._brain_runtime is not None

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
            body_generation=self.current_body_generation,
        )
        self.nervous_system.bind_body_port(
            self.current_body,
            body_generation=self.current_body_generation,
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
        self.nervous_system.bind_body_port(
            current,
            body_generation=self.body_binding.current_generation,
        )
        return current

    def unbind_body(self) -> BodyPort | None:
        previous = self.body_binding.unbind()
        self.nervous_system.bind_body_port(
            None,
            body_generation=None,
        )
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

    def configure_cognition(
        self,
        model_port: ModelPort,
        *,
        tool_port: ToolPort | None = None,
    ) -> None:
        if self._brain_runtime is not None:
            raise ElfieLifecycleError("Elfie cognition is already configured")
        if tool_port is None:
            candidate = getattr(model_port, "tool_port", None)
            if candidate is not None:
                tool_port = candidate

        def clock() -> datetime:
            return self.cognitive_datetime

        self._brain_runtime = assemble_brain_runtime(
            elfie_id=ElfieId(self.identity.elfie_id),
            workspace=self.perceptual_workspace,
            memory=self.memory,
            emotion=self.amygdala,
            homeostasis=self.hypothalamus,
            selfhood=self.selfhood,
            profile_anchors=self._profile_anchor_snapshot(clock()),
            nervous_system=self.nervous_system,
            communication=self.communication,
            skills=self.skills,
            current_body=lambda: self.current_body,
            current_body_generation=lambda: self.current_body_generation,
            clock=clock,
            model_port=model_port,
            tool_port=tool_port,
            activity_store=self.activity_store,
        )

    def start(self) -> None:
        self._require_brain_runtime().start()

    def stop(self) -> None:
        if self._brain_runtime is not None:
            self.communication.close()
            self.nervous_system.close_perception()
            self._brain_runtime.stop()

    def join(self) -> None:
        if self._brain_runtime is not None:
            self._brain_runtime.join()

    def advance_clock(self, seconds: float) -> None:
        if seconds < 0:
            raise InvalidClockDeltaError(seconds)
        with self._clock_lock:
            self._elapsed_time += seconds
            timestamp = self._elapsed_time
        self._require_brain_runtime().post_clock(timestamp)

    def pump_body_events(
        self,
        additional_events: Iterable[BodySensorEvent] = (),
    ) -> tuple[IngestReceipt, ...]:
        body = self.current_body
        generation = self.current_body_generation
        events = []
        if body is not None:
            events = [
                event.model_copy(update={"body_generation": generation or 1})
                for event in body.read_sensor_events()
            ]
        events.extend(additional_events)
        previous_urgent_revision = self.nervous_system.urgent_revision
        receipts = self.nervous_system.receive_body_events(events)
        retries = self.nervous_system.retry_pending()
        communication_retries = self.communication.retry_perception()
        if events or retries or communication_retries:
            self._require_brain_runtime().notify_perception(
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
            self._require_brain_runtime().notify_perception()
        return disposition

    def turn_outcomes(self) -> tuple[TurnOutcome, ...]:
        return self._require_brain_runtime().outcomes()

    def wait_for_outcome_count(self, count: int, *, timeout: float) -> None:
        self._require_brain_runtime().wait_for_outcome_count(count, timeout=timeout)

    def wait_for_output(self, turn_id: TurnId, *, timeout: float) -> None:
        self._require_brain_runtime().wait_for_output(turn_id, timeout=timeout)

    def execution_receipts(self, turn_id: TurnId) -> tuple[ExecutionReceipt, ...]:
        return self._require_brain_runtime().execution_receipts(turn_id)

    def turn_decision(self, turn_id: TurnId) -> TurnDecision | None:
        return self._require_brain_runtime().decision(turn_id)

    def turn_reasoning(self, turn_id: TurnId) -> ReasoningRunResult | None:
        return self._require_brain_runtime().reasoning(turn_id)

    def activities(self):
        """Return committed cross-Turn work for Observer/Lab projections."""
        return self._require_brain_runtime().activities()

    def orientation_snapshot(self) -> OrientationSnapshot:
        """Return the latest committed self/world orientation snapshot."""
        return self._require_brain_runtime().orientation_snapshot()

    def selfhood_snapshot(self) -> SelfhoodSnapshot:
        """Return the Brain-owned self-model, never the mutable Profile seed."""
        runtime = self._brain_runtime
        return (
            runtime.selfhood_snapshot()
            if runtime is not None
            else self.selfhood.snapshot()
        )

    def profile_anchor_snapshot(self) -> ProfileAnchorSnapshot:
        """Return the immutable identity/appearance projection used by Brain."""
        runtime = self._brain_runtime
        return (
            runtime.profile_anchors()
            if runtime is not None
            else self._profile_anchor_snapshot(self.cognitive_datetime)
        )

    def continuity_checkpoint(self) -> BrainContinuityCheckpoint:
        """Capture continuous Emotion/Energy/Memory state for restart tests."""
        return self._require_brain_runtime().continuity_checkpoint()

    def restore_continuity(self, checkpoint: BrainContinuityCheckpoint) -> None:
        """Restore a committed continuity checkpoint while Brain is stopped."""
        self._require_brain_runtime().restore_continuity(checkpoint)

    def _profile_anchor_snapshot(self, captured_at: datetime) -> ProfileAnchorSnapshot:
        profile = self.character_profile
        return ProfileAnchorSnapshot(
            revision=profile.schema_version,
            captured_at=captured_at,
            elfie_id=profile.identity.elfie_id,
            display_name=profile.identity.display_name,
            species_id=profile.identity.species_id,
            appearance_seed=profile.appearance.seed,
            appearance_genome_version=profile.appearance.genome_version,
            primary_morphology=profile.embodiment.primary_morphology,
        )

    def _require_brain_runtime(self) -> BrainRuntime:
        runtime = self._brain_runtime
        if runtime is None:
            raise ElfieLifecycleError("Elfie cognition is not configured")
        return runtime
