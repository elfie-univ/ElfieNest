from runtime.policy.food_policy import RuntimeTaskType, task_type_from_prompt


def test_task_type_detection_returns_food_task_only():
    assert task_type_from_prompt("请分析这个计划") is RuntimeTaskType.REASONING
    assert task_type_from_prompt("请运行 Python 代码") is RuntimeTaskType.CODE
    assert task_type_from_prompt("你好") is RuntimeTaskType.CHAT
