import importlib.util


def test_legacy_generation_fallback_modules_are_removed():
    assert importlib.util.find_spec("runtime.gateway.generation") is None
    assert importlib.util.find_spec("runtime.gateway.fallback") is None
