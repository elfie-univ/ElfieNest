import pytest

from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage


@pytest.fixture
def session_factory():
    sessions = []

    def create(spec, storage):
        session = ElfieLabSession(spec, storage)
        sessions.append(session)
        return session

    yield create

    for session in reversed(sessions):
        session.close()


def test_mock_turn_records_full_debug_chain(tmp_path, session_factory):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("艾菲-测试", species_id="dog")
    session = session_factory(spec, storage)

    profile = session.profile()
    assert profile["species_id"] == "dog"
    assert profile["appearance"]["species_id"] == "dog"
    assert len(profile["big_five"]) == 5
    assert len(profile["personality_tags"]) == 3
    assert set(profile["memory_cognition"]) == {
        "topics",
        "important_events",
        "relations",
        "knowledge",
        "world_understanding",
    }

    turn = session.run_turn(StimulusBundle(message="今天心情怎么样？"), "mock")

    assert turn["result"]["success"] is True
    assert turn["result"]["speech"]
    assert turn["model_call"]["model"] == "elfie-mock"
    stages = turn["trace"]["stages"]
    assert stages["typed_input"]["source"] == "developer_tool"
    assert stages["cognitive_turn"]["status"] == "completed"
    assert stages["cognitive_turn"]["model_mode"] == "text_fallback"
    assert stages["output_receipts"][-1]["status"] == "completed"
    assert (
        storage.load_latest_session(spec.elfie_id)["turns"][0]["turn_id"]
        == turn["turn_id"]
    )


def test_state_injection_is_visible_and_persistent(tmp_path, session_factory):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("边界测试")
    session = session_factory(spec, storage)

    turn = session.run_turn(
        StimulusBundle(
            message="你还好吗？",
            state_injection={"energy": 12, "fatigue": 88},
        ),
        "mock",
    )

    assert turn["used_state_injection"] is True
    assert turn["state_before"]["energy"] == 12.0
    assert turn["state_before"]["fatigue"] == 88.0
    assert "state_injection" in turn["trace"]["stages"]


def test_repeated_same_text_is_treated_as_two_events(tmp_path, session_factory):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("重复消息")
    session = session_factory(spec, storage)

    first = session.run_turn(StimulusBundle(message="你好"), "mock")
    second = session.run_turn(StimulusBundle(message="你好"), "mock")

    assert first["result"].get("filtered") is not True
    assert second["result"].get("filtered") is not True
    assert len(session.turns) == 2


def test_close_stops_cognitive_runtime(tmp_path, session_factory):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("关闭测试")
    session = session_factory(spec, storage)
    runtime = session.elfie._cognitive_runtime

    assert runtime is not None
    assert runtime.is_running is True

    session.close()

    assert runtime.is_running is False
