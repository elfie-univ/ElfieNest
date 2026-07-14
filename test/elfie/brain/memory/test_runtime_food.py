from elfie.brain.memory.runtime_food import ask_memory_model


class FoodRuntime:
    def __init__(self):
        self.kwargs = None

    def ask_with_food(self, **kwargs):
        self.kwargs = kwargs
        return "memory-result"


def test_memory_work_uses_food_interface_without_model_details(tmp_path):
    runtime = FoodRuntime()

    result = ask_memory_model(
        runtime,
        "整理记忆",
        elfie_id="elfie-1",
        config_dir=str(tmp_path),
        food_key="focus",
        complexity=2,
    )

    assert result == "memory-result"
    assert runtime.kwargs["food_key"] == "focus"
    assert runtime.kwargs["elfie_config_dir"] == str(tmp_path)
    assert "model" not in runtime.kwargs
