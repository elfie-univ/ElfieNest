from runtime.policy.food_policy import (
    DEFAULT_FOOD_POLICY,
    RuntimeTaskType,
    resolve_food_policy,
)


def test_default_food_policy_maps_task_types_to_model_groups():
    assert DEFAULT_FOOD_POLICY.group_for(RuntimeTaskType.CHAT) == "coarse"
    assert DEFAULT_FOOD_POLICY.group_for(RuntimeTaskType.REASONING) == "premium"
    assert DEFAULT_FOOD_POLICY.group_for(RuntimeTaskType.VISION) == "vision"
    assert DEFAULT_FOOD_POLICY.group_for(RuntimeTaskType.CODE) == "code"
    assert DEFAULT_FOOD_POLICY.group_for(RuntimeTaskType.ORGANIZE) == "organize"


def test_default_food_policy_accepts_string_task_type():
    assert DEFAULT_FOOD_POLICY.group_for("reasoning") == "premium"


def test_resolve_food_policy_returns_model_key_for_task_type():
    decision = resolve_food_policy(
        task_type="reasoning",
        available_model_keys={"local_fast", "remote_deep"},
    )

    assert decision.task_type == RuntimeTaskType.REASONING
    assert decision.group_key == "premium"
    assert decision.model_key == "remote_deep"


def test_resolve_food_policy_falls_back_to_local_fast_when_remote_unavailable():
    decision = resolve_food_policy(
        task_type="reasoning",
        available_model_keys={"local_fast"},
    )

    assert decision.group_key == "premium"
    assert decision.model_key == "local_fast"
