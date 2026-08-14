from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from devtools.nest_lab.world import NestLabWorld
from infrastructure.godot.gateway.messages import CommandName
from test.infrastructure.godot.gateway.fake_runtime import FakeRuntime


class _LabGateway(FakeRuntime):
    port = 8891
    handshake_nonce = "lab-test-nonce"

    def __init__(self) -> None:
        super().__init__()
        self.configured_revision: int | None = None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def mark_world_configured(self, connection, *, world_revision: int) -> None:
        assert connection == self.runtime_connection
        self.configured_revision = world_revision


class _PendingLabGateway(_LabGateway):
    def send_runtime_command(
        self,
        name,
        payload,
        *,
        world_revision: int,
        cause_id: str | None = None,
    ) -> str | None:
        if name is CommandName.EXECUTE_INTENT:
            self.commands.append((name, payload, world_revision))
            return cause_id
        return super().send_runtime_command(
            name,
            payload,
            world_revision=world_revision,
            cause_id=cause_id,
        )


def test_lab_translates_actor_and_wander_controls_to_v3_commands(tmp_path) -> None:
    # Given: a disposable Lab and a protocol-compatible Runtime, not the product engine.
    gateway = _LabGateway()
    gateway.connect()
    world = NestLabWorld(
        data_dir=tmp_path,
        http_port=8890,
        websocket_port=8891,
        gateway=gateway,
    )

    # When: the Runtime supplies its semantic manifest, then a developer adds a fox.
    world.poll()
    actor = world.add_actor("fox")
    world.set_wandering()

    # Then: only established protocol-v3 commands are emitted with semantic anchors.
    command_names = [command[0] for command in gateway.commands]
    assert gateway.configured_revision == 1
    assert command_names[0] is CommandName.CONFIGURE_WORLD
    assert CommandName.SYNC_ACTORS in command_names
    assert CommandName.EXECUTE_INTENT in command_names
    sync_payload = next(
        payload
        for name, payload, _ in gateway.commands
        if name is CommandName.SYNC_ACTORS and payload["actors"]
    )
    assert sync_payload["actors"] == [
        {
            "actor_id": actor.actor_id,
            "species": "fox",
            "home_anchor_id": "dorm-01/bed-01",
            "appearance": {},
        }
    ]


def test_pausing_wander_cancels_an_inflight_semantic_move(tmp_path) -> None:
    gateway = _PendingLabGateway()
    gateway.connect()
    world = NestLabWorld(
        data_dir=tmp_path,
        http_port=8890,
        websocket_port=8891,
        gateway=gateway,
    )
    world.poll()
    world.add_actor("dog")
    world.set_wandering()

    world.pause()

    assert [name for name, _, _ in gateway.commands].count(
        CommandName.CANCEL_INTENT
    ) == 1


def test_concurrent_actor_additions_preserve_capacity_and_unique_ids(tmp_path) -> None:
    """The polling frontend and control requests share one synchronized Lab state."""
    world = NestLabWorld(data_dir=tmp_path, http_port=8890, websocket_port=8891)
    world.set_bed_count(4)

    with ThreadPoolExecutor(max_workers=4) as executor:
        actors = list(executor.map(lambda _: world.add_actor("dog"), range(4)))

    assert len({actor.actor_id for actor in actors}) == 4
    assert world.world()["actor_count"] == 4
