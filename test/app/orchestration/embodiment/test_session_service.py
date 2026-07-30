"""Observable embodiment orchestration scenarios using real body binding."""

from __future__ import annotations

from pathlib import Path

from app.features.embodiment import EmbodimentConflict, Hosted, HostingFailed
from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.store import get_db, init_db
from app.orchestration.embodiment import EmbodimentSessionService
from elfie import Elfie
from elfie.body import HeadlessBody
from nest.embodiment import EmbodimentState


class FailingBody(HeadlessBody):
    """A real BodyPort whose connection path fails."""

    def connect(self) -> None:
        raise RuntimeError("连接失败")


def test_host_and_return_keep_one_real_active_body_and_persisted_state(
    tmp_path: Path,
) -> None:
    # Given: an at-nest Elfie and a registered database resident.
    db_path, elfie = _registered_elfie(tmp_path)
    nest_body = elfie.current_body
    assert nest_body is not None
    body = DeviceRegistry(db_path).enroll("00000001", "身体一", "toy")
    hosted_body = HeadlessBody(body_id=body.body_id)
    service = EmbodimentSessionService(db_path=db_path, nest_body_id=nest_body.body_id)

    # When: the Elfie is hosted and then returned through the service.
    hosted = service.host("00000001", elfie, hosted_body, lease_seconds=30)

    # Then: both body id and durable session prove that only toy-1 is active.
    assert isinstance(hosted, Hosted)
    assert elfie.current_body is hosted_body
    assert hosted_body.connected is True
    assert nest_body.connected is False
    assert get_embodiment_session(db_path, "00000001").body_id == body.body_id
    assert get_embodiment_session(db_path, "00000001").state is EmbodimentState.HOSTED

    returned = service.return_to_nest("00000001", elfie)

    assert returned.state is EmbodimentState.AT_NEST
    assert returned.body_id is None
    assert elfie.current_body is nest_body
    assert nest_body.connected is True
    assert hosted_body.connected is False
    assert get_embodiment_session(db_path, "00000001").state is EmbodimentState.AT_NEST


def test_host_failure_restores_the_nest_body_and_releases_the_persisted_lease(
    tmp_path: Path,
) -> None:
    # Given: a connected nest body and an external BodyPort that cannot connect.
    db_path, elfie = _registered_elfie(tmp_path)
    nest_body = elfie.current_body
    assert nest_body is not None
    service = EmbodimentSessionService(db_path=db_path, nest_body_id=nest_body.body_id)
    body = DeviceRegistry(db_path).enroll("00000001", "故障身体", "toy")

    # When: hosting attempts to bind the failed body after obtaining a lease.
    result = service.host(
        "00000001", elfie, FailingBody(body_id=body.body_id), lease_seconds=30
    )

    # Then: BodyBinding restores the exact prior body and persistence is at_nest.
    assert isinstance(result, HostingFailed)
    assert result.restored_state is EmbodimentState.AT_NEST
    assert elfie.current_body is nest_body
    assert nest_body.connected is True
    persisted = get_embodiment_session(db_path, "00000001")
    assert persisted.state is EmbodimentState.AT_NEST
    assert persisted.body_id is None


def test_duplicate_host_is_rejected_before_a_second_body_can_bind(
    tmp_path: Path,
) -> None:
    # Given: the first host operation owns the durable lease and active body.
    db_path, elfie = _registered_elfie(tmp_path)
    nest_body = elfie.current_body
    assert nest_body is not None
    service = EmbodimentSessionService(db_path=db_path, nest_body_id=nest_body.body_id)
    registry = DeviceRegistry(db_path)
    first_body = registry.enroll("00000001", "身体一", "toy")
    second_body = registry.enroll("00000001", "身体二", "toy")
    first = HeadlessBody(body_id=first_body.body_id)
    assert isinstance(service.host("00000001", elfie, first, lease_seconds=30), Hosted)

    # When: a second host request races in while the first session is active.
    result = service.host(
        "00000001",
        elfie,
        HeadlessBody(body_id=second_body.body_id),
        lease_seconds=30,
    )

    # Then: the conflict is explicit and toy-1 remains the single active binding.
    assert isinstance(result, EmbodimentConflict)
    assert elfie.current_body is first
    assert first.connected is True
    assert elfie.body_binding.current_body_id == first_body.body_id
    assert get_embodiment_session(db_path, "00000001").body_id == first_body.body_id


def test_heartbeat_timeout_unbinds_the_active_body_and_persists_offline(
    tmp_path: Path,
) -> None:
    # Given: a hosted body with an active persistence lease.
    db_path, elfie = _registered_elfie(tmp_path)
    nest_body = elfie.current_body
    assert nest_body is not None
    service = EmbodimentSessionService(db_path=db_path, nest_body_id=nest_body.body_id)
    body = DeviceRegistry(db_path).enroll("00000001", "身体一", "toy")
    hosted_body = HeadlessBody(body_id=body.body_id)
    hosted = service.host("00000001", elfie, hosted_body, lease_seconds=30)
    assert isinstance(hosted, Hosted)

    # When: the watchdog evaluates the session after its saved lease deadline.
    offline = service.expire_stale_lease(
        "00000001",
        elfie,
        now=(hosted.session.lease_expires_at or 0) + 1,
    )

    # Then: there is no active body and the persisted state/body id are observable.
    assert offline.state is EmbodimentState.OFFLINE
    assert offline.body_id is None
    assert elfie.current_body is None
    assert hosted_body.connected is False
    assert nest_body.connected is False
    persisted = get_embodiment_session(db_path, "00000001")
    assert persisted.state is EmbodimentState.OFFLINE
    assert persisted.body_id is None

    recovered = service.recover_to_nest("00000001", elfie)

    assert recovered.state is EmbodimentState.AT_NEST
    assert elfie.current_body is nest_body
    assert nest_body.connected is True


def _registered_elfie(tmp_path: Path) -> tuple[str, Elfie]:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id, username, password_hash, role) VALUES (1, ?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id, name, owner_user_id, species, adopted_at, status
               ) VALUES ('00000001', '测试精灵', 1, 'test', CURRENT_TIMESTAMP, 'offline')"""
        )
        connection.commit()
    nest_body = HeadlessBody(body_id="nest-1")
    nest_body.connect()
    return db_path, Elfie(
        elfie_id="00000001", memory_db_path=":memory:", body=nest_body
    )
