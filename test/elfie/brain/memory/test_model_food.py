from elfie.brain.memory.model_food import ask_memory_model


class FoodRuntime:
    def __init__(self):
        self.kwargs = None

    def ask_with_food(self, **kwargs):
        self.kwargs = kwargs
        return "memory-result"


def test_memory_work_uses_food_interface_without_model_details():
    runtime = FoodRuntime()

    result = ask_memory_model(
        runtime,
        "整理记忆",
        elfie_id="elfie-1",
        semantic_role="reasoning",
        complexity=2,
    )

    assert result == "memory-result"
    assert runtime.kwargs["food_key"] is None
    assert runtime.kwargs["semantic_role"] == "reasoning"
    assert runtime.kwargs["scene"] == "memory"
    assert "elfie_config_dir" not in runtime.kwargs
    assert "model" not in runtime.kwargs
