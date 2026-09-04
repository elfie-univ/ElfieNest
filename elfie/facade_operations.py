"""Operations exposed by the single-Elfie facade.

The public :class:`elfie.Elfie` class keeps construction and stable identity
properties in one place.  Runtime operations live in this internal mixin so
the facade remains a small aggregate boundary instead of becoming a second
Brain coordinator.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import Lock
from typing import Callable, Iterable

from elfie.body import BodyBinding, BodyRegistry
from elfie.body.contracts import BodySensorEvent
from elfie.body.port import BodyPort
from elfie.brain.activity.system import ActivityStorePort
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.journal import BrainJournalEntry, BrainJournalPort
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.context_types import CapabilityDescriptor
from elfie.brain.reasoning.decision_types import TurnDecision
from elfie.brain.reasoning.embodied_control import EmbodiedInputMode
from elfie.brain.reasoning.execution_types import ExecutionReceipt
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.model_port import ModelPort
from elfie.brain.reasoning.run import ReasoningRunResult
from elfie.brain.reasoning.skills import SkillManager
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.brain.reasoning.turn_outcome import TurnOutcome
from elfie.brain.runtime import BrainRuntime
from elfie.brain.selfhood.contracts import SelfhoodState
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.workspace.contracts import IngestReceipt
from elfie.brain.workspace.system import EventWorkspace
from elfie.brain_wiring import assemble_brain_runtime
from elfie.communication import CommunicationEnvelope, CommunicationHub
from elfie.communication.contracts import InboundDisposition, InboundDispositionStatus
from elfie.communication.perception_adapter import CommunicationPerceptionAdapter
from elfie.communication.router import RegisteredChannel
from elfie.lifecycle_errors import ElfieLifecycleError, InvalidClockDeltaError
from elfie.message_types import ElfieId, TurnId
from elfie.nervous_system import NervousSystem
from elfie.profile import (
    ElfieProfile,
    ProfileDossier,
    current_species_catalog,
)


class _ElfieFacadeState:
    """Typed state surface supplied by ``Elfie`` to the operation mixin."""

    _profile: ElfieProfile
    _energy: EnergySystem
    _selfhood: SelfhoodSystem
    _emotion: EmotionSystem
    _memory: MemorySystem
    _activity_store: ActivityStorePort
    _journal_store: BrainJournalPort
    _workspace: EventWorkspace
    _nervous_system: NervousSystem
    _body_registry: BodyRegistry
    _body_binding: BodyBinding
    _communication: CommunicationHub
    _skills: SkillManager
    _brain_runtime: BrainRuntime | None
    _reasoning_constitution: ReasoningConstitution | None
    _embodied_input_mode: EmbodiedInputMode
    _clock_lock: Lock
    _elapsed_time: float

    @property
    def identity(self):
        raise NotImplementedError

    @property
    def current_body(self) -> BodyPort | None:
        raise NotImplementedError

    @property
    def current_body_generation(self) -> int | None:
        raise NotImplementedError

    @property
    def cognitive_datetime(self) -> datetime:
        raise NotImplementedError

    @property
    def cognition_configured(self) -> bool:
        raise NotImplementedError


class ElfieFacadeOperations(_ElfieFacadeState):
    """Typed lifecycle, input and observation operations for ``Elfie``."""

    def bind_identity(self, elfie_id: str) -> None:
        if self.cognition_configured and elfie_id != self.identity.elfie_id:
            raise ElfieLifecycleError(
                "cannot change Elfie identity after cognition assembly"
            )
        identity_changed = self.identity.elfie_id != elfie_id
        self._memory.bind_elfie_identity(elfie_id)
        if identity_changed:
            self._profile = replace(
                self._profile,
                identity=replace(self.identity, elfie_id=elfie_id),
            )
            self._reassemble_perception_identity(ElfieId(elfie_id))
        self._communication.bind_identity(elfie_id)

    def _reassemble_perception_identity(self, elfie_id: ElfieId) -> None:
        """Rebuild empty pre-cognition producers under the final identity."""
        self._workspace = EventWorkspace(
            elfie_id,
            persistence=self._journal_store,
        )
        self._nervous_system = NervousSystem(
            perception_sink=self._workspace,
            elfie_id=elfie_id,
            body_port=self.current_body,
            body_generation=self.current_body_generation,
            logical_clock=lambda: self.cognitive_datetime,
        )
        self._nervous_system.bind_body_port(
            self.current_body,
            body_generation=self.current_body_generation,
        )
        if self._communication.perception_adapter is not None:
            self._communication.bind_perception_adapter(
                CommunicationPerceptionAdapter(self._workspace)
            )

    def register_body(self, body: BodyPort, *, make_current: bool = False) -> None:
        self._body_binding.register(body)
        if make_current:
            self.bind_body(body.body_id)

    def bind_body(self, body_id: str) -> BodyPort:
        current = self._body_binding.bind(body_id)
        self._nervous_system.bind_body_port(
            current,
            body_generation=self._body_binding.current_generation,
        )
        return current

    def unbind_body(self) -> BodyPort | None:
        previous = self._body_binding.unbind()
        self._nervous_system.bind_body_port(None, body_generation=None)
        return previous

    def register_communication_channel(
        self,
        channel: RegisteredChannel,
        *,
        connect: bool = False,
        replace: bool = False,
    ) -> RegisteredChannel:
        return self._communication.register_channel(
            channel,
            connect=connect,
            replace=replace,
        )

    def unregister_communication_channel(
        self,
        channel_id: str,
        *,
        expected: RegisteredChannel | None = None,
    ) -> bool:
        """Detach exactly the expected channel without racing a replacement."""
        current = self._communication.router.get(channel_id)
        if current is None or (expected is not None and current is not expected):
            return False
        current.disconnect()
        self._communication.router.unregister(channel_id)
        return True

    def configure_cognition(
        self,
        model_port: ModelPort,
        *,
        tool_port: ToolPort | None = None,
        world_capabilities: Callable[[], tuple[str, ...]] | None = None,
        world_capability_catalog: Callable[[], tuple[CapabilityDescriptor, ...]]
        | None = None,
        embodied_input_mode: EmbodiedInputMode | None = None,
    ) -> None:
        if self._brain_runtime is not None:
            raise ElfieLifecycleError("Elfie cognition is already configured")
        if not self._selfhood.snapshot().complete:
            raise ElfieLifecycleError(
                "Selfhood seed is missing or incomplete; cognition is unavailable"
            )
        if self._reasoning_constitution is None:
            raise ElfieLifecycleError(
                "Reasoning constitution is missing; cognition is unavailable"
            )
        if tool_port is None:
            candidate = getattr(model_port, "tool_port", None)
            if candidate is not None:
                tool_port = candidate

        def clock() -> datetime:
            return self.cognitive_datetime

        self._brain_runtime = assemble_brain_runtime(
            elfie_id=ElfieId(self.identity.elfie_id),
            workspace=self._workspace,
            memory=self._memory,
            emotion=self._emotion,
            homeostasis=self._energy,
            selfhood=self._selfhood,
            constitution=self._reasoning_constitution,
            nervous_system=self._nervous_system,
            communication=self._communication,
            skills=self._skills,
            current_body=lambda: self.current_body,
            current_body_generation=lambda: self.current_body_generation,
            world_capabilities=world_capabilities,
            world_capability_catalog=world_capability_catalog,
            clock=clock,
            model_port=model_port,
            embodied_input_mode=(
                embodied_input_mode
                if embodied_input_mode is not None
                else self._embodied_input_mode
            ),
            tool_port=tool_port,
            activity_store=self._activity_store,
            journal_store=self._journal_store,
            restore_clock=self._restore_cognitive_clock,
        )

    def _restore_cognitive_clock(self, captured_at: datetime) -> None:
        """Advance, never rewind, the facade clock before state restoration."""
        restored = captured_at.timestamp()
        with self._clock_lock:
            self._elapsed_time = max(self._elapsed_time, restored)

    def start(self) -> None:
        self._require_brain_runtime().start()

    def stop(self) -> None:
        if self._brain_runtime is not None:
            self._communication.close()
            self._nervous_system.close_perception()
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
            body.ingest_sensor_events(
                event.model_copy(update={"body_generation": generation or 1})
                for event in additional_events
            )
            events = [
                event.model_copy(update={"body_generation": generation or 1})
                for event in body.read_sensor_events()
            ]
        previous_urgent_revision = self._nervous_system.urgent_revision
        receipts = self._nervous_system.receive_body_events(events)
        retries = self._nervous_system.retry_pending()
        communication_retries = self._communication.retry_perception()
        if events or retries or communication_retries:
            self._require_brain_runtime().notify_perception(
                urgent_reason=(
                    "body_reflex"
                    if self._nervous_system.urgent_revision > previous_urgent_revision
                    else None
                )
            )
        return receipts + retries + communication_retries

    def receive_communication_envelope(
        self,
        envelope: CommunicationEnvelope,
    ) -> InboundDisposition:
        disposition = self._communication.receive_envelope(envelope)
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

    def close_resources(self) -> None:
        """Release durable stores owned by this Elfie after its runtime stops."""
        for resource in (self._journal_store, self._activity_store, self._memory):
            close = getattr(resource, "close", None)
            if callable(close):
                close()

    def brain_journal(self) -> tuple[BrainJournalEntry, ...]:
        """Return causal facts without exposing the mutable journal store."""
        runtime = self._brain_runtime
        if runtime is not None:
            return runtime.journal_entries()
        return self._journal_store.entries()

    def orientation_snapshot(self) -> OrientationSnapshot:
        """Return the latest committed self/world orientation snapshot."""
        return self._require_brain_runtime().orientation_snapshot()

    def selfhood_snapshot(self) -> SelfhoodState:
        """Return the Brain-owned self-model, never the mutable Profile seed."""
        runtime = self._brain_runtime
        return (
            runtime.selfhood_snapshot()
            if runtime is not None
            else self._selfhood.snapshot()
        )

    def profile_dossier(self) -> ProfileDossier:
        """Return the Profile-owned immutable external identity dossier."""
        return self._profile_dossier(self.cognitive_datetime)

    def motivation_snapshot(self) -> MotivationSnapshot:
        """Return the Brain-owned fixed-drive snapshot for observation."""
        runtime = self._brain_runtime
        if runtime is None:
            return MotivationSnapshot.unknown().model_copy(
                update={"captured_at": self.cognitive_datetime}
            )
        return runtime.motivation_snapshot()

    def consolidation_snapshot(self):
        """Expose bounded quiet-window memory整理 state for Lab/Observer reads."""
        runtime = self._brain_runtime
        if runtime is None:
            from elfie.brain.consolidation.contracts import (
                CognitiveConsolidationSnapshot,
            )

            return CognitiveConsolidationSnapshot.unknown().model_copy(
                update={"captured_at": self.cognitive_datetime}
            )
        return runtime.consolidation_snapshot()

    def continuity_checkpoint(self) -> BrainContinuityCheckpoint:
        """Capture continuous Emotion/Energy/Memory state for restart tests."""
        return self._require_brain_runtime().continuity_checkpoint()

    def restore_continuity(self, checkpoint: BrainContinuityCheckpoint) -> None:
        """Restore a committed continuity checkpoint while Brain is stopped."""
        self._require_brain_runtime().restore_continuity(checkpoint)

    def _profile_dossier(self, captured_at: datetime) -> ProfileDossier:
        profile = self._profile
        origin = profile.identity.origin
        species = current_species_catalog().definition(profile.identity.species_id)
        return ProfileDossier(
            revision=profile.schema_version,
            captured_at=captured_at,
            elfie_id=profile.identity.elfie_id,
            display_name=profile.identity.display_name,
            species_id=profile.identity.species_id,
            species_name=species.display_name,
            species_shape=species.earth_shape_label,
            gender=profile.identity.gender,
            age_years=origin.age_years,
            origin_place_id=origin.origin_place_id,
            origin_place_label=origin.origin_place_label,
            appearance_genome_version=profile.appearance.genome_version,
        )

    def _require_brain_runtime(self) -> BrainRuntime:
        runtime = self._brain_runtime
        if runtime is None:
            raise ElfieLifecycleError("Elfie cognition is not configured")
        return runtime


__all__ = ("ElfieFacadeOperations",)
