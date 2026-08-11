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
from elfie import ElfieFactory
from elfie.brain.food_port import MainFoodSelection
from elfie.factory import ElfieAssembly
from elfie.initialization import assemble_profile
from infrastructure.godot import GodotGateway, GodotTransport, NativeBody
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.models.runtime_adapter import (
    SerializedRuntimeAdapter,
    StructuredRuntime,
)
from infrastructure.persistence.data_home import (
    get_elfie_config_dir,
    get_elfie_workspace_dir,
)
from infrastructure.persistence.elfies import SQLiteElfiesProjectionAdapter
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

MainFoodLoader = Callable[[str], Optional[Union[str, MainFoodSelection]]]


@dataclass(frozen=True)
class NestSessionServices:
    """One assembled live Nest and its injected Runtime boundaries."""

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
    runtime: StructuredRuntime,
    godot_ws_port: int,
    http_port: int,
    tick_interval_sec: float,
    main_food_loader: MainFoodLoader | None = None,
) -> NestSessionServices:
    """Construct the existing Engine without starting any lifecycle-owned channel."""
    world_runtime = GodotNestSessionAdapter(
        port=godot_ws_port,
        http_port=http_port,
    )

    def model_port_factory(elfie_id: str) -> SerializedRuntimeAdapter:
        return SerializedRuntimeAdapter(
            runtime,
            food_key_resolver=lambda: (
                main_food_loader(elfie_id) if main_food_loader is not None else None
            ),
            elfie_workspace_resolver=lambda: str(get_elfie_workspace_dir(elfie_id)),
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
                    body=NativeBody(
                        body_id=row.elfie_id,
                        transport=GodotTransport(
                            cast(GodotGateway, session.world_runtime)
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
    profile = assemble_profile(config_dir=None, elfie_id=elfie_id, supplied=None)
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=NativeBody(
                body_id=elfie_id,
                transport=GodotTransport(cast(GodotGateway, session.world_runtime)),
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
