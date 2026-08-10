from unittest.mock import MagicMock

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from nest.godot_gateway.messages import CommandName
from test.nest.godot_gateway.fake_runtime import FakeRuntime


def test_fake_runtime_reconnect_converges_complete_actor_catalog() -> None:
    runtime = FakeRuntime()
    runtime.connect()
    engine = ElfieNestEngine(GodotNestSessionAdapter(gateway=runtime))
    engine.session.register_elfie("fox-1", MagicMock(spec=Elfie))
    engine.session.register_elfie("dog-1", MagicMock(spec=Elfie))

    engine.tick_once(0.0)
    engine.tick_once(0.0)
    engine.tick_once(0.0)

    assert runtime.actor_ids == ("dog-1", "fox-1")
    assert [command[0] for command in runtime.commands[:2]] == [
        CommandName.CONFIGURE_WORLD,
        CommandName.SYNC_ACTORS,
    ]
    first_sync_count = sum(
        command[0] is CommandName.SYNC_ACTORS for command in runtime.commands
    )
    runtime.disconnect()
    engine.tick_once(0.0)
    runtime.connect()
    engine.tick_once(0.0)
    engine.tick_once(0.0)
    engine.tick_once(0.0)

    assert runtime.actor_ids == ("dog-1", "fox-1")
    assert (
        sum(command[0] is CommandName.SYNC_ACTORS for command in runtime.commands)
        == first_sync_count + 1
    )
