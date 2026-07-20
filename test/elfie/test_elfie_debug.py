from elfie import Elfie
from elfie.body import HeadlessBody


class MockRuntimeAgent:
    class Config:
        providers = {"ollama": {"api_key": "", "api_base": "mock://local"}}

    config = Config()

    def ask(self, prompt, energy, task_complexity):
        return "听到了哒。[ACTION]nod_head[/ACTION]"


def test_perceive_and_respond_populates_optional_debug_trace():
    elfie = Elfie(memory_db_path=":memory:")
    trace = {}

    result = elfie.perceive_and_respond(
        {
            "message_id": "turn-1",
            "has_new_message": True,
            "user_message": "你好",
            "temperature": 24.0,
            "salience_score": 20.0,
        },
        MockRuntimeAgent(),
        debug_trace=trace,
    )

    assert result["success"] is True
    assert trace["raw_input"]["message_id"] == "turn-1"
    assert trace["stages"]["decision"]["attention_mode"] == "CEN"
    assert trace["stages"]["execution"]["action"] == "nod_head"
    assert trace["stages"]["memory_write"]["written"] is True


def test_standalone_elfie_uses_in_memory_graph_by_default():
    # Given / When
    elfie = Elfie()

    # Then
    assert elfie.memory.storage.db_path == ":memory:"


def test_headless_body_drives_existing_perception_chain_without_rewriting_it():
    body = HeadlessBody(body_id="elfie-test:headless")
    body.connect()
    body.inject_sensor_data(
        {
            "message_id": "turn-body-1",
            "has_new_message": True,
            "user_message": "你好",
            "temperature": 24.0,
            "salience_score": 20.0,
        }
    )
    elfie = Elfie(memory_db_path=":memory:", body=body)
    trace = {}

    result = elfie.perceive_body_and_respond(MockRuntimeAgent(), debug_trace=trace)

    assert result["success"] is True
    assert result["action"] == "nod_head"
    assert result["body_execution"]["status"] == "completed"
    assert result["body_execution"]["action"] == "nod_head"
    assert trace["raw_input"]["message_id"] == "turn-body-1"
    assert trace["raw_input"]["sensory_events"][0]["sensor"] == "stimulus_bundle"
    assert trace["stages"]["body_output"]["action"] == "nod_head"
