import pytest

import devtools.elfie_lab.session as session_module
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
        "world_model",
        "world_understanding",
    }

    turn = session.run_turn(StimulusBundle(message="今天心情怎么样？"), "mock")

    assert turn["result"]["success"] is True
    assert turn["result"]["speech"]
    assert turn["stimulus_bundle"]["source_domain"] == "communication"
    assert turn["decision"]["message_texts"] == [turn["result"]["speech"]]
    assert turn["decision"]["motion_intents"] == []
    assert "response" not in turn["model_call"]
    assert turn["model_call"]["model"] == "elfie-mock"
    stages = turn["trace"]["stages"]
    assert stages["typed_input"]["source"] == "developer_tool"
    assert stages["typed_input"]["source_domain"] == "communication"
    assert stages["turn_boundary"]["source_domain"] == "communication"
    assert stages["cognitive_turn"]["status"] == "completed"
    assert stages["cognitive_turn"]["model_mode"] == "structured"
    assert stages["reasoning"]["status"] == "completed"
    assert [step["kind"] for step in stages["reasoning"]["steps"]] == [
        "model",
        "verify",
    ]
    assert stages["output_receipts"][-1]["status"] == "completed"
    assert (
        storage.load_latest_session(spec.elfie_id)["turns"][0]["turn_id"]
        == turn["turn_id"]
    )


def test_mock_embodied_turn_uses_body_output_only(tmp_path, session_factory):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("具身链路")
    session = session_factory(spec, storage)

    turn = session.run_turn(
        StimulusBundle(source_domain="embodied", message="现场有人叫你"),
        "mock",
    )

    assert turn["trace"]["stages"]["turn_boundary"]["source_domain"] == "embodied"
    assert turn["decision"]["message_intents"] == []
    assert turn["decision"]["spoken_texts"]
    assert turn["decision"]["motion_intents"][0]["motion"] == "nod_head"


def test_mock_activity_wakes_and_settles_from_child_receipt(tmp_path, session_factory):
    # Given: a communication turn that creates a bounded future Activity.
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("跨回合精灵")
    session = session_factory(spec, storage)

    first = session.run_turn(StimulusBundle(message="请提醒我稍后带钥匙"), "mock")

    # When: the fake clock reaches the Activity wake-up and the resulting
    # Internal Turn is allowed to settle its communication step.
    assert first["decision"]["activity_intents"]
    assert session.snapshot()["activities"][0]["state"] == "waiting"
    session.elfie.advance_clock(31)
    session.elfie._brain_runtime.coordinator.synchronize(2)
    session.elfie.advance_clock(12)
    session.elfie.wait_for_outcome_count(3, timeout=5)
    for outcome in session.elfie.turn_outcomes():
        session.elfie.wait_for_output(outcome.turn_id, timeout=5)

    # Then: durable state reaches a receipt-backed terminal state exactly once.
    activity = session.snapshot()["activities"][0]
    assert activity["state"] == "completed"
    assert activity["progress"][0]["attempts"] == 1
    assert activity["progress"][0]["last_receipt_id"]
    assert len(session._turn_adapter.channel.sent) == 2

    # And: a new Lab session observes the same terminal Activity without replay.
    session.close()
    restored = ElfieLabSession(spec, storage)
    try:
        assert restored.snapshot()["activities"][0]["state"] == "completed"
        assert restored.snapshot()["activities"][0]["progress"][0]["attempts"] == 1
        assert restored._turn_adapter.channel.sent == []
    finally:
        restored.close()


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
    runtime = session.elfie._brain_runtime

    assert runtime is not None
    assert runtime.is_running is True

    session.close()

    assert runtime.is_running is False


def test_close_if_idle_refuses_to_interrupt_owned_turn_lock(tmp_path, session_factory):
    # Given
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("并发删除测试")
    session = session_factory(spec, storage)
    session._lock.acquire()

    try:
        # When
        closed = session.close_if_idle()
    finally:
        session._lock.release()

    # Then
    assert closed is False
    assert session.elfie._brain_runtime.is_running is True


def test_closed_session_reference_cannot_start_turn_after_delete_wins_race(
    tmp_path, session_factory
):
    # Given
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("删除抢先测试")
    session = session_factory(spec, storage)
    assert session.close_if_idle() is True

    # When / Then
    with pytest.raises(RuntimeError, match="会话已关闭"):
        session.run_turn(StimulusBundle(message="不应执行"), "mock")


def test_failed_turn_does_not_persist_exception_secrets_or_paths(
    tmp_path, session_factory, monkeypatch
):
    storage = ElfieLabStorage(str(tmp_path))
    spec = storage.create_elfie("失败脱敏测试")
    session = session_factory(spec, storage)

    def fail_runtime(_food_key, _config_dir, **_kwargs):
        raise RuntimeError(f"sk-sensitive-secret at {tmp_path}/config.yaml")

    monkeypatch.setattr(session_module, "create_runtime", fail_runtime)

    turn = session.run_turn(StimulusBundle(message="触发失败"), "mock")
    persisted = str(storage.load_latest_session(spec.elfie_id))

    assert turn["error"] == "RuntimeError"
    assert "sk-sensitive-secret" not in persisted
    assert str(tmp_path) not in persisted
