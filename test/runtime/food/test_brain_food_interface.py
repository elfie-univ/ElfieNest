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
