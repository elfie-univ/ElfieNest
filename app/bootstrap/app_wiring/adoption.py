"""Production assembly for Adoption and accepted-resident admission."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional, cast

from app.features.adoption import (
    AdoptionService,
    CandidatePortraitPort,
    SpeciesRuntimeReadinessPort,
)
from app.features.configuration.settings import SettingsStorePort
from app.orchestration.nest_session import NestSession
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie.genesis import CandidateReveal, GenesisCandidateReveal, GenesisSourcePackage
from elfie.public import (
    BodyPort,
    ElfieFactory,
    GenesisCandidate,
    GenesisCompiler,
    ReasoningConstitution,
)
from infrastructure.godot import GodotGateway, GodotTransport, NativeBody
from infrastructure.godot.artifacts.species_package_validation import (
    run_godot_species_validation,
)
from infrastructure.godot.artifacts.species_runtime_catalog import (
    build_species_runtime_catalog,
)
from infrastructure.godot.body_transport import (
    RuntimeIntentPayload,
    RuntimeIntentResult,
)
from infrastructure.persistence.activity import SQLiteActivityStoreAdapter
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter
from infrastructure.persistence.configuration.bundled_defaults import (
    load_emotion_dynamics_defaults,
    load_emotion_expression_defaults,
    load_nest_config,
    load_reasoning_constitution,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.species_assets import (
    BundledSpeciesPresentationAdapter,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.platform import (
    ElfieFactoryAdapter,
    SettingsAdoptionPolicyAdapter,
)
from infrastructure.skills import BundledSkillCatalog
from nest.public import NestConfig


@dataclass(frozen=True)
class AdoptionServices:
    adoption: AdoptionService
    resident_admission: ResidentAdmissionService


def build_adoption_services(
    db_path: str,
    *,
    settings: SettingsStorePort,
    nest_session: NestSession | None,
    portraits: CandidatePortraitPort | None = None,
    nest_config: NestConfig | None = None,
    catalog: Any | None = None,
    species_runtime: SpeciesRuntimeReadinessPort | None = None,
) -> AdoptionServices:
    catalog = catalog or load_and_configure_species_catalog()
    if species_runtime is None:
        species_runtime = build_species_runtime_catalog(
            catalog,
            godot_runner=run_godot_species_validation,
        )

    def body_factory(elfie_id: str, _workspace: str) -> BodyPort | None:
        if nest_session is None:
            return None
        return NativeBody(
            body_id=elfie_id,
            transport=GodotTransport(
                cast(GodotGateway, nest_session.world_runtime),
                actor_id=elfie_id,
                speech_intent=cast(
                    Callable[[RuntimeIntentPayload], bool],
                    nest_session.prepare_speech,
                ),
                semantic_action=cast(
                    Callable[[RuntimeIntentPayload], Optional[str]],
                    nest_session.prepare_semantic_action,
                ),
                semantic_action_result=cast(
                    Callable[[RuntimeIntentPayload, RuntimeIntentResult], None],
                    nest_session.complete_semantic_action,
                ),
                visual_observation=cast(
                    Callable[[RuntimeIntentPayload], bool],
                    nest_session.prepare_visual_observation,
                ),
            ),
        )

    adoption_persistence = SQLiteAdoptionAdapter(
        db_path,
        nest_config=nest_config or load_nest_config(),
    )

    @lru_cache(maxsize=1)
    def load_source() -> GenesisSourcePackage:
        """Keep the published source lazy and shared by both Genesis paths."""

        return load_genesis_source_package()

    class LazyCandidateReveal:
        def __init__(self) -> None:
            self._adapter: GenesisCandidateReveal | None = None

        def reveal(self, candidate: GenesisCandidate) -> CandidateReveal:
            if self._adapter is None:
                self._adapter = GenesisCandidateReveal(load_source())
            return self._adapter.reveal(candidate)

    adoption = AdoptionService(
        SettingsAdoptionPolicyAdapter(settings),
        adoption_persistence,
        portraits=portraits,
        candidate_reveal=LazyCandidateReveal(),
        catalog=catalog,
        species_presentation=BundledSpeciesPresentationAdapter(catalog=catalog),
        species_runtime=species_runtime,
    )

    def build_genesis_compiler() -> GenesisCompiler:
        """Load the creation source only when a new resident is compiled.

        Committed residents must be restorable after the bundled source is no
        longer available.  ResidentAdmission remains the sole compiler caller;
        this closure only defers construction until its compiling state.
        """

        return GenesisCompiler(
            load_source(),
            catalog=catalog,
        )

    return AdoptionServices(
        adoption=adoption,
        resident_admission=ResidentAdmissionService(
            adoption,
            FinalElfieWorkspaceAdapter.from_database_path(db_path),
            ElfieFactoryAdapter(
                ElfieFactory(),
                body_factory,
                lambda workspace: YamlProfileStoreAdapter(Path(workspace) / "profile"),
                lambda workspace: SQLiteMemoryStoreAdapter(
                    Path(workspace) / "memory" / "knowledge.sqlite",
                    elfie_id=Path(workspace).name,
                ),
                lambda workspace: SQLiteActivityStoreAdapter(
                    Path(workspace) / "activity" / "activity.sqlite"
                ),
                lambda workspace: SQLiteBrainJournalAdapter(
                    Path(workspace) / "brain" / "journal.sqlite"
                ),
                lambda workspace: YamlSelfhoodSeedAdapter(
                    Path(workspace) / "brain"
                ).load(),
                lambda workspace: YamlEnergyLimitsAdapter(
                    Path(workspace) / "brain"
                ).load(),
                emotion_expression_config=load_emotion_expression_defaults(),
                emotion_dynamics_config=load_emotion_dynamics_defaults(),
                reasoning_constitution=ReasoningConstitution.from_mapping(
                    load_reasoning_constitution()
                ),
                skill_catalog=BundledSkillCatalog(),
            ),
            nest_session,
            build_genesis_compiler,
            admission_store=adoption_persistence,
        ),
    )


__all__ = ("AdoptionServices", "build_adoption_services")
