from elfie import ElfieIndividual


class MockRuntimeAgent:
    class Config:
        providers = {"ollama": {"api_key": "", "api_base": "mock://local"}}

    config = Config()

    def ask(self, prompt, energy, task_complexity):
        return "听到了哒。[ACTION]nod_head[/ACTION]"


def test_perceive_and_respond_populates_optional_debug_trace():
    elfie = ElfieIndividual(memory_db_path=":memory:")
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
