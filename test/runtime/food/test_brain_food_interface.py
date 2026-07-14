from elfie.brain.brain_types import BrainContext, SensorData
from elfie.brain.cognition.brain import NeocortexBrain


class FoodAwareRuntime:
    def __init__(self):
        self.call = None

    def ask_with_food(self, **kwargs):
        self.call = kwargs
        return "收到"


def test_brain_passes_only_semantic_food_intent_to_runtime():
    runtime = FoodAwareRuntime()
    brain = NeocortexBrain(elfie_id="elfie-1")

    brain.think_and_decide(
        BrainContext(
            sensors=SensorData(
                has_new_message=True,
                user_message="请分析这个复杂方案",
            )
        ),
        runtime,
    )

    assert runtime.call["food_key"] == "focus"
    assert runtime.call["elfie_id"] == "elfie-1"
    assert "model" not in runtime.call
    assert "reasoning" not in runtime.call


def test_brain_passes_config_directory_and_media_without_model_details(tmp_path):
    runtime = FoodAwareRuntime()
    brain = NeocortexBrain(config_dir=str(tmp_path), elfie_id="elfie-1")

    brain.think_and_decide(
        BrainContext(
            sensors=SensorData(
                has_new_message=True,
                user_message="看看图片",
                images=("/tmp/image.png",),
            )
        ),
        runtime,
    )

    assert runtime.call["food_key"] == "vision"
    assert runtime.call["elfie_config_dir"] == str(tmp_path)
    assert runtime.call["images"] == ["/tmp/image.png"]
