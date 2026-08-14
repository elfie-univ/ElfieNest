"""Production assembly for the live Nest Session workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union, cast

from app.orchestration.nest_session import (
    ElfieNestEngine,
    ModelPortFactory,
    NestSession,
)
from elfie.public import (
    ElfieAssembly,
    ElfieFactory,
    MainFoodSelection,
    assemble_profile,
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
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.layout.data_home import get_elfie_config_dir
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

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


def build_nest_session_services(
    db_path: str,
    *,
    model_execution: StructuredModelExecution,
    godot_ws_port: int,
    http_port: int,
    tick_interval_sec: float,
    main_food_loader: MainFoodLoader | None = None,
) -> NestSessionServices:
    """Construct the existing Engine without starting any lifecycle-owned channel."""
    gateway = GodotAPIServer(
        host="127.0.0.1",
        port=godot_ws_port,
        http_port=http_port,
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
            nest_repository=SQLiteNestStateAdapter(db_path),
        ),
        world_runtime=world_runtime,
        model_port_factory=model_port_factory,
    )


def restore_registered_elfies(
    db_path: str,
    session: NestSession,
) -> ElfieRestoreResult:
    """Restore the existing persisted Elfies and register them in one Nest Session."""
    factory = ElfieFactory()
    restored: list[RestoredElfie] = []
    failures: list[ElfieRestoreFailure] = []
    for row in SQLiteElfiesProjectionAdapter(db_path).list_directory():
        try:
            config_dir = Path(get_elfie_config_dir(row.elfie_id))
            profile_store = YamlProfileStoreAdapter(config_dir / "profile")
            profile = profile_store.load()
            memory_store = SQLiteMemoryStoreAdapter(
                config_dir / "memory" / "knowledge.sqlite"
            )
            elfie = factory.restore(
                ElfieAssembly(
                    profile=profile,
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


def register_transient_elfie(session: NestSession, elfie_id: str) -> None:
    """Create and register the existing interactive-script Elfie."""
    profile = assemble_profile(elfie_id=elfie_id, supplied=None)
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=NativeBody(
                body_id=elfie_id,
                transport=GodotTransport(
                    cast(GodotGateway, session.world_runtime),
                    actor_id=elfie_id,
                    speech_intent=cast(
                        Callable[[RuntimeIntentPayload], bool], session.prepare_speech
                    ),
                    semantic_action=cast(
                        Callable[[RuntimeIntentPayload], Optional[str]],
                        session.prepare_semantic_action,
                    ),
                    semantic_action_result=cast(
                        Callable[[RuntimeIntentPayload, RuntimeIntentResult], None],
                        session.complete_semantic_action,
                    ),
                ),
            ),
        ),
    )
    session.register_elfie(elfie_id, elfie)


__all__ = (
    "ElfieRestoreFailure",
    "ElfieRestoreResult",
    "MainFoodLoader",
    "NestSessionServices",
    "RestoredElfie",
    "build_nest_session_services",
    "register_transient_elfie",
    "restore_registered_elfies",
)
