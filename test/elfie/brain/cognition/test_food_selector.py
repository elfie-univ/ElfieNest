from elfie.brain.brain_types import BrainContext, SensorData
from elfie.brain.cognition.food_selector import ElfieFoodSelector


def test_salience_requests_emergency_food():
    intent = ElfieFoodSelector().select(
        "SN",
        BrainContext(sensors=SensorData(salience_score=90)),
    )

    assert intent.food_key == "emergency"
    assert intent.scene == "salience"


def test_tool_task_only_enables_network_tool_when_online():
    selector = ElfieFoodSelector()

    online = selector.select(
        "CEN",
        BrainContext(
            sensors=SensorData(user_message="搜索并读取文件", is_network_online=True)
        ),
    )
    offline = selector.select(
        "CEN",
        BrainContext(
            sensors=SensorData(user_message="搜索并读取文件", is_network_online=False)
        ),
    )

    assert online.food_key == "tool"
    assert online.allowed_tools == ("web_search", "local_file", "code_sandbox")
    assert "web_search" not in offline.allowed_tools


def test_emotion_peak_can_request_but_not_authorize_premium_food():
    intent = ElfieFoodSelector().select(
        "CEN",
        BrainContext(emotion_mood="fear", emotion_intensity=90),
    )

    assert intent.food_key == "premium"


def test_reasoning_and_creative_tasks_have_distinct_foods():
    selector = ElfieFoodSelector()

    reasoning = selector.select(
        "CEN", BrainContext(sensors=SensorData(user_message="分析这个复杂方案"))
    )
    creative = selector.select(
        "CEN", BrainContext(sensors=SensorData(user_message="创作一个故事"))
    )

    assert reasoning.food_key == "focus"
    assert creative.food_key == "creative"
