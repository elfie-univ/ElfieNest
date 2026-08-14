"""Single-Elfie facade and lifecycle boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from elfie.body import BodyBinding, BodyRegistry
from elfie.body.port import BodyPort
from elfie.brain.activity.system import ActivityStorePort, InMemoryActivityStore
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.journal import BrainJournalPort, InMemoryBrainJournal
from elfie.brain.memory.memory_store import MemoryStorePort
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.reasoning.model_port import ModelPort
from elfie.brain.reasoning.skills import SkillManager
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.brain.runtime import BrainRuntime
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.workspace.system import EventWorkspace
from elfie.communication import CommunicationHub
from elfie.facade_operations import ElfieFacadeOperations
from elfie.initialization import assemble_anatomy
from elfie.message_types import ElfieId
from elfie.nervous_system import NervousSystem
from elfie.profile import (
    ELFARIA_CANON,
    ElfieProfile,
    get_species_canon_for_technical_id,
)


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
        journal_store: BrainJournalPort | None = None,
    ) -> None:
        character_profile.validate()
        self._profile = character_profile
        self._elapsed_time = 0.0
        self._clock_lock = Lock()
        self._energy = EnergySystem(
            self._profile.system_limits,
            clock=lambda: self._elapsed_time,
        )
        self._selfhood = SelfhoodSystem.from_personality_data(
            _selfhood_seed(self._profile),
            initial_at=self.cognitive_datetime,
            profile_revision=self._profile.schema_version,
        )
        self._emotion = EmotionSystem(
            personality=self._selfhood.big_five_dict(),
            clock=lambda: self._elapsed_time,
        )
        self._memory = MemorySystem(
            elfie_id=self._profile.identity.elfie_id,
            personality_data=self._selfhood.seed_data(
                display_name=self._profile.identity.display_name
            ),
            storage=memory_store,
            clock=lambda: self.cognitive_datetime,
            initial_at=self.cognitive_datetime,
        )
        self._activity_store = activity_store or InMemoryActivityStore()
        self._journal_store = journal_store or InMemoryBrainJournal()
        workspace_id = ElfieId(self._profile.identity.elfie_id)
        self._workspace = EventWorkspace(
            workspace_id,
            persistence=self._journal_store,
        )
        self._nervous_system = NervousSystem(
            self._profile.capabilities,
            perception_sink=self._workspace,
            elfie_id=workspace_id,
            body_port=body,
        )
        self._anatomy_type, self._anatomy = assemble_anatomy(
            self._profile,
        )
        self._body_registry = BodyRegistry()
        self._body_binding = BodyBinding(self._body_registry)
        self._body_binding.attach(body)
        self._nervous_system.bind_body_port(
            body,
            body_generation=self._body_binding.current_generation,
        )
        self._communication = communication or CommunicationHub(str(workspace_id))
        self._communication.bind_identity(str(workspace_id))
        self._skills = skills or SkillManager()
        self._brain_runtime: BrainRuntime | None = None
        if model_port is not None:
            self.configure_cognition(model_port, tool_port=tool_port)

    @property
    def profile(self) -> ElfieProfile:
        return self._profile

    @property
    def identity(self):
        return self._profile.identity

    @property
    def species_id(self) -> str:
        return self._profile.identity.species_id

    @property
    def anatomy_type(self) -> str:
        """Return the stable morphology label without exposing mutable anatomy."""
        return self._anatomy_type

    @property
    def current_body(self) -> BodyPort | None:
        return self._body_binding.current

    @property
    def current_body_generation(self) -> int | None:
        """Authority generation for the currently selected Body, if any."""
        return self._body_binding.current_generation

    @property
    def current_body_id(self) -> str | None:
        """Return the bound Body identity without exposing its mutable registry."""
        return self._body_binding.current_body_id

    def has_body(self, body_id: str) -> bool:
        """Return whether a Body is registered without leaking the registry owner."""
        return self._body_registry.get(body_id) is not None

    def is_registered_body(self, body: BodyPort) -> bool:
        """Return whether this exact Body instance owns its registered identity."""
        return self._body_registry.get(body.body_id) is body

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


def _selfhood_seed(profile: ElfieProfile) -> dict[str, object]:
    """Merge legacy personality presentation with immutable canon facts.

    The Profile remains the objective authority. These values are copied into
    Brain Selfhood only as the Elfie's initial self-understanding, so ordinary
    conversation cannot silently replace its species or origin.
    """
    seed = dict(profile.personality)
    species = get_species_canon_for_technical_id(profile.identity.species_id)
    origin = profile.identity.origin
    region_name = (
        ELFARIA_CANON.known_region_name
        if origin.home_region_id == ELFARIA_CANON.known_region_id
        else origin.home_region_id
    )
    fixed_description = (
        f"我叫 {profile.identity.display_name}，是一只 {species.display_name}"
        f"（{species.earth_shape_label}），来自 {ELFARIA_CANON.display_name} 的 {region_name}。"
        "我自愿参加赴地计划，来到地球后住进自己的 ElfieNest；对不知道的事情，我会先说明不确定。"
    )
    seed["self_description"] = fixed_description
    seed["species_name"] = species.display_name
    seed["identity_facts"] = (
        f"正式物种名是 {species.display_name}，{species.earth_shape_label} 只是地球侧形态说明。",
        f"来自 {ELFARIA_CANON.display_name} 的 {region_name}。",
        ELFARIA_CANON.earth_arrival_statement,
        f"{ELFARIA_CANON.earth_home_name} 是在地球生活的基地和家；我的身份和记忆属于我自己。",
    )
    seed["knowledge_boundaries"] = ELFARIA_CANON.knowledge_boundaries
    seed["behavior_anchors"] = species.earth_first_contact_cues
    seed["norms"] = (
        "尊重自愿选择。",
        "对不确定保持诚实。",
        "把真实经历和推测分开。",
    )
    return seed
