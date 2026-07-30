from elfie.brain.memory.runtime_food import ask_memory_model


class _Runtime:
    def ask_with_food(self, **kwargs):
        self.kwargs = kwargs
        return "ok"


def test_brain_requests_semantic_role_not_compiled_food():
    runtime = _Runtime()
    assert ask_memory_model(
        runtime,
        "remember",
        elfie_id="elfie_1",
        config_dir="/tmp/elfie",
        semantic_role="reasoning",
        complexity=2,
    ) == "ok"
    assert runtime.kwargs["semantic_role"] == "reasoning"
    assert runtime.kwargs["food_key"] is None
