from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage


def test_mock_turn_records_full_debug_chain(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("艾菲-测试", species_id="dog")
    session = ElfieLabSession(spec, storage)

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
    assert turn["trace"]["stages"]["sensory_filter"]["passed"] is True
    assert turn["trace"]["stages"]["decision"]["attention_mode"] == "CEN"
    assert "thalamus_context" in turn["trace"]["stages"]
    assert "action_validation" in turn["trace"]["stages"]
    assert turn["result"]["body_execution"]["status"] == "completed"
    assert turn["trace"]["stages"]["body_output"]["action"] == turn["result"]["action"]
    assert session.body.last_result.action == turn["result"]["action"]
    assert turn["state_before"]["energy"] > turn["state_after"]["energy"]
    assert (
        storage.load_latest_session(spec.elfie_id)["turns"][0]["turn_id"]
        == turn["turn_id"]
    )


def test_state_injection_is_visible_and_persistent(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("边界测试")
    session = ElfieLabSession(spec, storage)

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


def test_repeated_same_text_is_treated_as_two_events(tmp_path):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("重复消息")
    session = ElfieLabSession(spec, storage)

    first = session.run_turn(StimulusBundle(message="你好"), "mock")
    second = session.run_turn(StimulusBundle(message="你好"), "mock")

    assert first["result"].get("filtered") is not True
    assert second["result"].get("filtered") is not True
    assert len(session.turns) == 2
