"""Production assembly for the live Nest Session workflow."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Optional, Union, cast

from app.orchestration.nest_session import (
    ElfieNestEngine,
    ModelPortFactory,
    NestSession,
)
from elfie.public import (
    ElfieAssembly,
    ElfieFactory,
    MainFoodSelection,
    ReasoningConstitution,
)
from infrastructure.godot import GodotGateway, GodotTransport, NativeBody
from infrastructure.godot.body_transport import (
    RuntimeIntentPayload,
    RuntimeIntentResult,
)
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.models.model_execution_adapter import (
    SerializedModelExecutionAdapter,
    StructuredModelExecution,
)
from infrastructure.persistence.activity import SQLiteActivityStoreAdapter
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
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.layout.data_home import get_elfie_config_dir
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from nest.public import NestConfig

if TYPE_CHECKING:
    from infrastructure.platform.lifecycle.endpoint_binding import (
        BoundServiceEndpoints,
    )

MainFoodLoader = Callable[[str], Optional[Union[str, MainFoodSelection]]]


@dataclass(frozen=True)
class NestSessionServices:
    """One assembled live Nest and its injected execution boundaries."""

    engine: ElfieNestEngine
    world_runtime: GodotNestSessionAdapter
    model_port_factory: ModelPortFactory


@dataclass(frozen=True)
class RestoredElfie:
    elfie_id: str
    name: str


@dataclass(frozen=True)
class ElfieRestoreFailure:
    elfie_id: str
    name: str
    error: str


@dataclass(frozen=True)
class ElfieRestoreResult:
    restored: tuple[RestoredElfie, ...]
    failures: tuple[ElfieRestoreFailure, ...]


def load_emotion_expression_config():
    """Expose bundled emotion defaults through the Bootstrap boundary."""
    return load_emotion_expression_defaults()


def load_emotion_dynamics_config():
    """Expose bundled emotion dynamics through the Bootstrap boundary."""
    return load_emotion_dynamics_defaults()


def bind_service_endpoints(
    http_port: int,
    websocket_port: int,
    *,
    automatic: bool = False,
    host: str = "127.0.0.1",
) -> BoundServiceEndpoints:
    """Resolve the concrete endpoint binder at the system composition root."""
    from infrastructure.platform.lifecycle.endpoint_binding import (
        bind_service_endpoints as bind,
    )

    return bind(
        http_port,
        websocket_port,
        automatic=automatic,
        host=host,
    )


def build_nest_session_services(
    db_path: str,
    *,
    model_execution: StructuredModelExecution,
    godot_ws_port: int,
    http_port: int,
    tick_interval_sec: float,
    godot_socket: socket.socket | None = None,
    main_food_loader: MainFoodLoader | None = None,
    nest_config: NestConfig | None = None,
) -> NestSessionServices:
    """Construct the existing Engine without starting any lifecycle-owned channel."""
    selected_nest_config = nest_config or load_nest_config()
    gateway = GodotAPIServer(
        host="127.0.0.1",
        port=godot_ws_port,
        http_port=http_port,
        prebound_socket=godot_socket,
    )
    world_runtime = GodotNestSessionAdapter(
        gateway=gateway,
    )

    def model_port_factory(elfie_id: str) -> SerializedModelExecutionAdapter:
        return SerializedModelExecutionAdapter(
            model_execution,
            scope_id=elfie_id,
            food_key_resolver=lambda: (
                main_food_loader(elfie_id) if main_food_loader is not None else None
            ),
        )

    return NestSessionServices(
        engine=ElfieNestEngine(
            world_runtime,
            tick_interval_sec=tick_interval_sec,
            state_store=SQLiteNestStateAdapter(
                db_path,
                nest_config=selected_nest_config,
            ),
            nest_config=selected_nest_config,
        ),
        world_runtime=world_runtime,
        model_port_factory=model_port_factory,
    )


def restore_registered_elfies(
    db_path: str,
    session: NestSession,
    *,
    emotion_expression_config: Mapping[str, object] | None = None,
    emotion_dynamics_config: Mapping[str, object] | None = None,
    reasoning_constitution: ReasoningConstitution | None = None,
) -> ElfieRestoreResult:
    """Restore the existing persisted Elfies and register them in one Nest Session."""
    emotion_expression_config = (
        emotion_expression_config
        if emotion_expression_config is not None
        else load_emotion_expression_defaults()
    )
    emotion_dynamics_config = (
        emotion_dynamics_config
        if emotion_dynamics_config is not None
        else load_emotion_dynamics_defaults()
    )
    reasoning_constitution = (
        reasoning_constitution
        if reasoning_constitution is not None
        else ReasoningConstitution.from_mapping(load_reasoning_constitution())
    )
    # Restoration validates each persisted profile through the domain's injected
    # species catalog. The foreground service restores residents before it
    # constructs the HTTP application container, so this bootstrap boundary must
    # establish that catalog before invoking ElfieFactory.
    load_and_configure_species_catalog()
    factory = ElfieFactory()
    restored: list[RestoredElfie] = []
    failures: list[ElfieRestoreFailure] = []
    for row in SQLiteElfiesProjectionAdapter(db_path).list_directory():
        try:
            config_dir = Path(get_elfie_config_dir(row.elfie_id))
            profile_store = YamlProfileStoreAdapter(config_dir / "profile")
            profile = profile_store.load()
            memory_store = SQLiteMemoryStoreAdapter(
                config_dir / "memory" / "knowledge.sqlite",
                elfie_id=row.elfie_id,
            )
            elfie = factory.restore(
                ElfieAssembly(
                    profile=profile,
                    selfhood_seed=YamlSelfhoodSeedAdapter(config_dir / "brain").load(),
                    reasoning_constitution=reasoning_constitution,
                    energy_limits=YamlEnergyLimitsAdapter(config_dir / "brain").load(),
                    emotion_expression_config=emotion_expression_config,
                    emotion_dynamics_config=emotion_dynamics_config,
                    memory_store=memory_store,
                    activity_store=SQLiteActivityStoreAdapter(
                        config_dir / "activity" / "activity.sqlite"
                    ),
                    journal_store=SQLiteBrainJournalAdapter(
                        config_dir / "brain" / "journal.sqlite"
                    ),
                    body=NativeBody(
                        body_id=row.elfie_id,
                        transport=GodotTransport(
                            cast(GodotGateway, session.world_runtime),
                            actor_id=row.elfie_id,
                            speech_intent=cast(
                                Callable[[RuntimeIntentPayload], bool],
                                session.prepare_speech,
                            ),
                            semantic_action=cast(
                                Callable[[RuntimeIntentPayload], Optional[str]],
                                session.prepare_semantic_action,
                            ),
                            semantic_action_result=cast(
                                Callable[
                                    [RuntimeIntentPayload, RuntimeIntentResult], None
                                ],
                                session.complete_semantic_action,
                            ),
                        ),
                    ),
                ),
            )
            session.register_elfie(row.elfie_id, elfie)
            restored.append(RestoredElfie(row.elfie_id, row.name))
        except Exception as error:  # noqa: BLE001 - preserve per-Elfie startup isolation
            failures.append(
                ElfieRestoreFailure(
                    elfie_id=row.elfie_id,
                    name=row.name,
                    error=str(error),
                )
            )
    return ElfieRestoreResult(tuple(restored), tuple(failures))


__all__ = (
    "ElfieRestoreFailure",
    "ElfieRestoreResult",
    "MainFoodLoader",
    "NestSessionServices",
    "RestoredElfie",
    "build_nest_session_services",
    "restore_registered_elfies",
)
