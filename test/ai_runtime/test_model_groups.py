import importlib.util


def test_model_groups_module_is_removed_from_runtime_surface():
    assert importlib.util.find_spec("ai_runtime.models.groups") is None
