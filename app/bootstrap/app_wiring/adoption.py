"""Production assembly for Adoption and accepted-resident admission."""

from __future__ import annotations

from dataclasses import dataclass
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
from elfie.public import BodyPort, ElfieFactory
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
from infrastructure.models.adoption_narrative import (
    AdoptionStructuredModelExecution,
    StructuredAdoptionNarrativeAdapter,
)
from infrastructure.persistence.activity import SQLiteActivityStoreAdapter
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter
from infrastructure.persistence.configuration.bundled_defaults import (
    load_emotion_expression_defaults,
    load_nest_config,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.species_assets import (
    BundledSpeciesPresentationAdapter,
)
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
    model_execution: AdoptionStructuredModelExecution | None = None,
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
            ),
        )

    narrative = (
        None
        if model_execution is None
        else StructuredAdoptionNarrativeAdapter(model_execution)
    )
    adoption = AdoptionService(
        SettingsAdoptionPolicyAdapter(settings),
        SQLiteAdoptionAdapter(
            db_path,
            nest_config=nest_config or load_nest_config(),
        ),
        portraits=portraits,
        narrative=narrative,
        catalog=catalog,
        species_presentation=BundledSpeciesPresentationAdapter(catalog=catalog),
        species_runtime=species_runtime,
    )
    return AdoptionServices(
        adoption=adoption,
        resident_admission=ResidentAdmissionService(
            adoption,
            FinalElfieWorkspaceAdapter.from_database_path(db_path, catalog=catalog),
            ElfieFactoryAdapter(
                ElfieFactory(),
                body_factory,
                lambda workspace: YamlProfileStoreAdapter(Path(workspace) / "profile"),
                lambda workspace: SQLiteMemoryStoreAdapter(
                    Path(workspace) / "memory" / "knowledge.sqlite"
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
            ),
            nest_session,
        ),
    )


__all__ = ("AdoptionServices", "build_adoption_services")
