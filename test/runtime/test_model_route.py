import importlib.util


def test_model_route_module_is_removed_from_runtime_surface():
    assert importlib.util.find_spec("runtime.policy.model_route") is None


def test_global_model_router_module_is_removed_from_runtime_surface():
    assert importlib.util.find_spec("runtime.policy.router") is None
