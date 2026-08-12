"""Single-Elfie facade and lifecycle boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from elfie.body import BodyBinding, BodyRegistry
from elfie.body.port import BodyPort
from elfie.brain.activity import ActivityStorePort, InMemoryActivityStore
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.runtime import BrainRuntime
from elfie.brain.runtime_port import ModelPort
from elfie.brain.selfhood import SelfhoodSystem
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.communication import CommunicationHub
from elfie.facade_operations import ElfieFacadeOperations
from elfie.initialization import assemble_anatomy
from elfie.message_types import ElfieId
from elfie.nervous_system import NervousSystem
from elfie.profile import ElfieProfile


class Elfie(ElfieFacadeOperations):
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
