from app.interfaces.api.runtime_routes import _runtime_policy_payload


def test_runtime_policy_has_no_task_to_food_routes():
    payload = _runtime_policy_payload({})
    assert "task_routes" not in payload
    assert "food_keys" not in payload
