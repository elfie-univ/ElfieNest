from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.accounts import AccountsService
from app.features.elfies import ElfiesService
from app.orchestration.observer import (
    CloseObserverSessionCommand,
    NextObserverFrameQuery,
    ObserverDeltaResult,
    ObserverEntityRecord,
    ObserverFacade,
    ObserverForbidden,
    ObserverFrameResult,
    ObserverPrincipal,
    ObserverRateLimited,
    ObserverSessionExpired,
    ObserverSnapshotResult,
    ObserverSubscription,
    ObserverWorldIntent,
    OpenObserverSessionCommand,
    SubmitObserverIntentCommand,
    UpdateObserverInterestCommand,
)


class MutableClock:
    def __init__(self) -> None:
        self.current = 10.0

    def now(self) -> float:
        return self.current


class FixedCapabilities:
    def __init__(self) -> None:
        self.sequence = 0

    def issue(self) -> str:
        self.sequence += 1
        return f"observer_{self.sequence}"


class MemoryWorld:
    def __init__(self) -> None:
        self.entities = (_entity("fox-1", posture="awake"),)
        self.intents: list[ObserverWorldIntent] = []

    def list_entities(self) -> tuple[ObserverEntityRecord, ...]:
        return self.entities

    def submit_intent(self, intent: ObserverWorldIntent) -> None:
        self.intents.append(intent)


class ConcurrentWorld(MemoryWorld):
    def __init__(self) -> None:
        super().__init__()
        self.barrier: Barrier | None = None

    def list_entities(self) -> tuple[ObserverEntityRecord, ...]:
        if self.barrier is not None:
            self.barrier.wait(timeout=2.0)
        return super().list_entities()


def _facade(
    *,
    visible_ids: tuple[str, ...] = ("fox-1",),
    max_intents: int = 12,
    session_ttl_seconds: int = 120,
    world: MemoryWorld | None = None,
) -> tuple[ObserverFacade, MutableClock, MemoryWorld]:
    accounts = MagicMock(spec=AccountsService)
    accounts.session_ttl_seconds.return_value = 30
    elfies = MagicMock(spec=ElfiesService)
    elfies.list_visible.return_value = tuple(
        SimpleNamespace(profile=SimpleNamespace(elfie_id=elfie_id))
        for elfie_id in visible_ids
    )
    clock = MutableClock()
    selected_world = world or MemoryWorld()
    return (
        ObserverFacade(
            accounts=accounts,
            elfies=elfies,
            world=selected_world,
            clock=clock,
            capabilities=FixedCapabilities(),
            max_intents_per_window=max_intents,
            session_ttl_seconds=session_ttl_seconds,
        ),
        clock,
        selected_world,
    )


def test_member_capability_is_bound_to_owned_elfie_and_login_session() -> None:
    facade, _clock, _world = _facade()
    member = ObserverPrincipal(user_id=7, access="member")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=member,
            session_fingerprint="login-one",
            subscription=ObserverSubscription(kind="elfie", elfie_id="fox-1"),
        )
    ).capability

    with pytest.raises(ObserverForbidden, match="invalid observer capability"):
        facade.next_frame(
            NextObserverFrameQuery(
                principal=member,
                session_fingerprint="login-two",
                capability=capability,
                acknowledged_generation=None,
                acknowledged_sequence=None,
            )
        )
    with pytest.raises(ObserverForbidden, match="cannot observe"):
        facade.open_session(
            OpenObserverSessionCommand(
                principal=member,
                session_fingerprint="login-one",
                subscription=ObserverSubscription(kind="elfie", elfie_id="owl-1"),
            )
        )


def test_projection_emits_snapshot_delta_and_stale_cursor_resync() -> None:
    facade, _clock, world = _facade()
    manager = ObserverPrincipal(user_id=1, access="manager")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    ).capability
    initial = facade.next_frame(
        NextObserverFrameQuery(manager, "owner-login", capability, None, None)
    )
    assert isinstance(initial, ObserverSnapshotResult)
    assert initial.entities[0].state.posture == "awake"

    world.entities = (_entity("fox-1", posture="resting"),)
    delta = facade.next_frame(
        NextObserverFrameQuery(
            manager,
            "owner-login",
            capability,
            initial.generation,
            initial.sequence,
        )
    )
    assert isinstance(delta, ObserverDeltaResult)
    assert [(change.field, change.value) for change in delta.changes] == [
        ("posture", "resting")
    ]

    world.entities = (_entity("fox-1", posture="sleeping"),)
    resync = facade.next_frame(
        NextObserverFrameQuery(
            manager,
            "owner-login",
            capability,
            initial.generation,
            initial.sequence,
        )
    )
    assert isinstance(resync, ObserverSnapshotResult)
    assert resync.entities[0].state.posture == "sleeping"


def test_single_entity_membership_change_emits_snapshot() -> None:
    facade, _clock, world = _facade(visible_ids=("fox-1", "owl-1"))
    manager = ObserverPrincipal(user_id=1, access="manager")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    ).capability
    initial = facade.next_frame(
        NextObserverFrameQuery(manager, "owner-login", capability, None, None)
    )
    assert isinstance(initial, ObserverSnapshotResult)

    world.entities = (
        _entity("fox-1", posture="awake"),
        _entity("owl-1", posture="resting"),
    )
    added = facade.next_frame(
        NextObserverFrameQuery(
            manager,
            "owner-login",
            capability,
            initial.generation,
            initial.sequence,
        )
    )
    assert isinstance(added, ObserverSnapshotResult)
    assert [entity.state.entity_id for entity in added.entities] == ["fox-1", "owl-1"]

    world.entities = (_entity("owl-1", posture="resting"),)
    removed = facade.next_frame(
        NextObserverFrameQuery(
            manager,
            "owner-login",
            capability,
            added.generation,
            added.sequence,
        )
    )
    assert isinstance(removed, ObserverSnapshotResult)
    assert [entity.state.entity_id for entity in removed.entities] == ["owl-1"]


def test_one_stale_session_cannot_break_another_viewer() -> None:
    facade, _clock, world = _facade(visible_ids=("fox-1", "owl-1"))
    manager = ObserverPrincipal(user_id=1, access="manager")
    first = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    ).capability
    assert isinstance(
        facade.next_frame(
            NextObserverFrameQuery(manager, "owner-login", first, None, None)
        ),
        ObserverSnapshotResult,
    )

    world.entities = (
        _entity("fox-1", posture="awake"),
        _entity("owl-1", posture="resting"),
    )
    second = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    ).capability

    frame = facade.next_frame(
        NextObserverFrameQuery(manager, "owner-login", second, None, None)
    )
    assert isinstance(frame, ObserverSnapshotResult)
    assert [entity.state.entity_id for entity in frame.entities] == ["fox-1", "owl-1"]


def test_different_viewers_publish_concurrently_without_a_global_session_lock() -> None:
    world = ConcurrentWorld()
    facade, _clock, _world = _facade(world=world)
    manager = ObserverPrincipal(user_id=1, access="manager")
    capabilities = tuple(
        facade.open_session(
            OpenObserverSessionCommand(
                principal=manager,
                session_fingerprint="owner-login",
                subscription=ObserverSubscription(kind="room", room_id="local-nest"),
            )
        ).capability
        for _ in range(2)
    )
    initial = tuple(
        facade.next_frame(
            NextObserverFrameQuery(manager, "owner-login", capability, None, None)
        )
        for capability in capabilities
    )
    assert all(isinstance(frame, ObserverSnapshotResult) for frame in initial)
    world.entities = (_entity("fox-1", posture="resting"),)
    world.barrier = Barrier(2)

    def next_for(index: int) -> ObserverFrameResult | None:
        frame = initial[index]
        assert frame is not None
        return facade.next_frame(
            NextObserverFrameQuery(
                manager,
                "owner-login",
                capabilities[index],
                frame.generation,
                frame.sequence,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(next_for, range(2)))

    assert all(isinstance(frame, ObserverDeltaResult) for frame in results)


def test_observer_lease_renews_while_active_and_expires_independently() -> None:
    facade, clock, _world = _facade(session_ttl_seconds=120)
    manager = ObserverPrincipal(user_id=1, access="manager")
    opened = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    )
    assert opened.idle_timeout_seconds == 120
    initial = facade.next_frame(
        NextObserverFrameQuery(manager, "owner-login", opened.capability, None, None)
    )
    assert isinstance(initial, ObserverSnapshotResult)

    clock.current = 100.0
    assert (
        facade.next_frame(
            NextObserverFrameQuery(
                manager,
                "owner-login",
                opened.capability,
                initial.generation,
                initial.sequence,
            )
        )
        is None
    )

    clock.current = 219.0
    assert (
        facade.next_frame(
            NextObserverFrameQuery(
                manager,
                "owner-login",
                opened.capability,
                initial.generation,
                initial.sequence,
            )
        )
        is None
    )

    clock.current = 340.0
    with pytest.raises(ObserverSessionExpired):
        facade.next_frame(
            NextObserverFrameQuery(
                manager,
                "owner-login",
                opened.capability,
                initial.generation,
                initial.sequence,
            )
        )


def test_close_session_is_idempotent_and_isolated() -> None:
    facade, _clock, _world = _facade()
    manager = ObserverPrincipal(user_id=1, access="manager")
    opened = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    )
    command = CloseObserverSessionCommand(
        principal=manager,
        session_fingerprint="owner-login",
        capability=opened.capability,
    )

    facade.close_session(command)
    facade.close_session(command)

    with pytest.raises(ObserverForbidden, match="invalid observer capability"):
        facade.next_frame(
            NextObserverFrameQuery(
                manager,
                "owner-login",
                opened.capability,
                None,
                None,
            )
        )


def test_interest_cannot_widen_scope_and_intents_keep_existing_rate_limit() -> None:
    facade, clock, world = _facade(max_intents=1, session_ttl_seconds=30)
    member = ObserverPrincipal(user_id=7, access="member")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=member,
            session_fingerprint="member-login",
            subscription=ObserverSubscription(kind="elfie", elfie_id="fox-1"),
        )
    ).capability
    with pytest.raises(ObserverForbidden, match="cannot change"):
        facade.update_interest(
            UpdateObserverInterestCommand(
                principal=member,
                session_fingerprint="member-login",
                capability=capability,
                subscription=ObserverSubscription(kind="room", room_id="local-nest"),
                visible_entity_ids=None,
            )
        )

    intent = ObserverWorldIntent(actor_id="fox-1", interaction="greet")
    command = SubmitObserverIntentCommand(
        principal=member,
        session_fingerprint="member-login",
        capability=capability,
        intent=intent,
    )
    facade.submit_intent(command)
    with pytest.raises(ObserverRateLimited):
        facade.submit_intent(command)
    assert world.intents == [intent]

    clock.current = 41.0
    with pytest.raises(ObserverSessionExpired, match="observer session expired"):
        facade.submit_intent(command)


def test_room_sessions_are_filtered_per_principal_and_room() -> None:
    facade, _clock, world = _facade(visible_ids=("fox-1",))
    world.entities = (
        _entity("fox-1", posture="awake", room_id="room-1"),
        _entity("owl-1", posture="resting", room_id="room-2"),
    )
    member = ObserverPrincipal(user_id=7, access="member")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=member,
            session_fingerprint="member-login",
            subscription=ObserverSubscription(kind="room", room_id="room-1"),
        )
    ).capability

    frame = facade.next_frame(
        NextObserverFrameQuery(member, "member-login", capability, None, None)
    )

    assert isinstance(frame, ObserverSnapshotResult)
    assert [entity.state.entity_id for entity in frame.entities] == ["fox-1"]


def test_logout_revokes_every_capability_for_the_login_session() -> None:
    facade, _clock, _world = _facade()
    manager = ObserverPrincipal(user_id=1, access="manager")
    capability = facade.open_session(
        OpenObserverSessionCommand(
            principal=manager,
            session_fingerprint="owner-login",
            subscription=ObserverSubscription(kind="room", room_id="local-nest"),
        )
    ).capability

    facade.revoke_session("owner-login")

    with pytest.raises(ObserverForbidden, match="invalid observer capability"):
        facade.next_frame(
            NextObserverFrameQuery(manager, "owner-login", capability, None, None)
        )


def _entity(
    entity_id: str,
    *,
    posture: str,
    room_id: str = "local-nest",
) -> ObserverEntityRecord:
    return ObserverEntityRecord(
        entity_id=entity_id,
        room_id=room_id,
        zone_id=None,
        posture=posture,
        active=True,
        active_command_id=None,
        species_id="fox",
        appearance=(),
        home_anchor_id=None,
    )
