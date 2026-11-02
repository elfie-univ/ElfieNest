from __future__ import annotations

import pytest

from app.orchestration.nest_session import (
    ElfieNestEngine,
    NestStateStoreError,
    RuntimeConnection,
    WorldEvent,
    WorldEventName,
)
from app.orchestration.nest_session.models import (
    SceneManifest,
    SemanticWorldCatalog,
    WorldAnchor,
    WorldZone,
)
from nest.config import NestConfigError
from nest.public import (
    AnchorKind,
    InteractionAnchor,
    NestSnapshot,
    PersistentResidentState,
    ResidentPresence,
    WorldCatalog,
    ZoneDescriptor,
)
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


class RecordingNestStateStore:
    def __init__(self) -> None:
        self.fail_writes = False
        self.snapshot = NestSnapshot(
            desired_bed_count=32,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )

    def load_snapshot(self) -> NestSnapshot:
        return self.snapshot

    def initialize_snapshot(self, snapshot: NestSnapshot) -> None:
        self.save_snapshot(snapshot)

    def save_snapshot(self, snapshot: NestSnapshot) -> None:
        if self.fail_writes:
            raise NestStateStoreError("injected write failure")
        self.snapshot = snapshot


def test_bed_count_command_survives_ticks_and_session_restart() -> None:
    store = RecordingNestStateStore()
    engine = ElfieNestEngine(FakeWorldRuntime(), state_store=store)

    engine.session.update_bed_count(32)
    for _ in range(3):
        engine.tick_once(1.0)

    assert engine.nest.desired_bed_count == 32
    assert store.snapshot.desired_bed_count == 32

    restarted = ElfieNestEngine(FakeWorldRuntime(), state_store=store)
    assert restarted.nest.desired_bed_count == 32


def test_fixed_bed_count_does_not_reconfigure_runtime() -> None:
    runtime = FakeWorldRuntime()
    runtime.connection = RuntimeConnection("runtime-a", 1)
    store = RecordingNestStateStore()
    engine = ElfieNestEngine(runtime, state_store=store)

    engine.tick_once(0.0)
    assert runtime.configurations == [("local-nest", 32, 1)]

    engine.session.update_bed_count(32)
    assert runtime.configurations == [("local-nest", 32, 1)]
    with pytest.raises(NestConfigError, match="固定为 32"):
        engine.session.update_bed_count(4)
    assert engine.nest.desired_bed_count == 32


def test_bed_count_command_rolls_back_live_nest_when_persistence_fails() -> None:
    store = RecordingNestStateStore()
    engine = ElfieNestEngine(FakeWorldRuntime(), state_store=store)
    store.fail_writes = True

    with pytest.raises(NestStateStoreError, match="injected write failure"):
        engine.session.update_bed_count(32)

    assert engine.nest.desired_bed_count == 32
    assert store.snapshot.desired_bed_count == 32


def test_home_assignment_survives_ticks_and_session_restart() -> None:
    store = RecordingNestStateStore()
    store.snapshot = NestSnapshot(
        desired_bed_count=32,
        elapsed_seconds=0.0,
        catalog=_persisted_catalog(),
        residents=(
            PersistentResidentState(
                elfie_id="00000001",
                presence=ResidentPresence.PENDING_RUNTIME,
            ),
        ),
    )
    engine = ElfieNestEngine(FakeWorldRuntime(), state_store=store)

    engine.session.assign_home("00000001", "dorm-01/bed-02")
    for _ in range(3):
        engine.tick_once(1.0)

    assert store.snapshot.residents[0].home_anchor_id == "dorm-01/bed-02"
    restarted = ElfieNestEngine(FakeWorldRuntime(), state_store=store)
    assert restarted.nest.home_anchor_id("00000001") == "dorm-01/bed-02"


def test_admission_finalization_assigns_home_before_runtime_registration() -> None:
    store = RecordingNestStateStore()
    store.snapshot = NestSnapshot(
        desired_bed_count=32,
        elapsed_seconds=0.0,
        catalog=_persisted_catalog(),
        residents=(),
    )
    engine = ElfieNestEngine(FakeWorldRuntime(), state_store=store)

    engine.session.finalize_admission("admission-1", "00000001")
    engine.session.finalize_admission("admission-1", "00000001")

    assert engine.nest.home_anchor_id("00000001") == "dorm-01/bed-01"
    assert engine.session.elfie_items_snapshot() == ()
    assert store.snapshot.residents[0].home_anchor_id == "dorm-01/bed-01"


def _manifest_event(*, revision: int, bed_count: int) -> WorldEvent:
    return WorldEvent(
        event_id=f"manifest-{revision}",
        connection=RuntimeConnection("runtime-a", 1),
        world_revision=revision,
        name=WorldEventName.SCENE_MANIFEST,
        payload=SceneManifest(
            SemanticWorldCatalog(
                nest_id="local-nest",
                revision=revision,
                zones=(
                    WorldZone(
                        zone_id="dorm-01",
                        label="Dorm",
                        order=0,
                        anchors=tuple(
                            WorldAnchor(
                                anchor_id=f"dorm-01/bed-{index:02d}",
                                kind="bed",
                                label=f"Bed {index}",
                                order=index - 1,
                                active=True,
                            )
                            for index in range(1, bed_count + 1)
                        ),
                    ),
                ),
            )
        ),
    )


def _persisted_catalog() -> WorldCatalog:
    return WorldCatalog(
        nest_id="local-nest",
        revision=1,
        zones=(
            ZoneDescriptor(
                zone_id="dorm-01",
                label="Dorm",
                order=0,
                anchors=tuple(
                    InteractionAnchor(
                        anchor_id=f"dorm-01/bed-{index:02d}",
                        kind=AnchorKind.BED,
                        label=f"Bed {index}",
                        order=index - 1,
                    )
                    for index in range(1, 5)
                ),
            ),
        ),
    )
