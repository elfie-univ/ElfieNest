from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.accounts import AccountsService
from app.features.elfies import ElfiesService
from app.orchestration.observer import (
    NextObserverFrameQuery,
    ObserverDeltaResult,
    ObserverEntityRecord,
    ObserverFacade,
    ObserverForbidden,
    ObserverPrincipal,
    ObserverRateLimited,
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


def _facade(
    *,
    visible_ids: tuple[str, ...] = ("fox-1",),
    max_intents: int = 12,
) -> tuple[ObserverFacade, MutableClock, MemoryWorld]:
    accounts = MagicMock(spec=AccountsService)
    accounts.session_ttl_seconds.return_value = 30
    elfies = MagicMock(spec=ElfiesService)
    elfies.list_visible.return_value = tuple(
        SimpleNamespace(profile=SimpleNamespace(elfie_id=elfie_id))
        for elfie_id in visible_ids
    )
    clock = MutableClock()
    world = MemoryWorld()
    return (
        ObserverFacade(
            accounts=accounts,
            elfies=elfies,
            world=world,
            clock=clock,
            capabilities=FixedCapabilities(),
            max_intents_per_window=max_intents,
        ),
        clock,
        world,
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


def test_interest_cannot_widen_scope_and_intents_keep_existing_rate_limit() -> None:
    facade, clock, world = _facade(max_intents=1)
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
    with pytest.raises(ObserverForbidden, match="invalid observer capability"):
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
