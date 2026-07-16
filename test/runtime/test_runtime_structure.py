def test_layered_runtime_imports_are_available():
    from runtime.gateway.agent import RuntimeAgent
    from runtime.models.catalog import ModelCatalog
    from runtime.models.registry import ModelRegistry
    from runtime.providers.ollama import OllamaManager
    from runtime.providers.profiles import get_profile
    from runtime.safety.permissions import PermissionManager
    from runtime.storage.data_home import get_elfie_home
    from runtime.tools.code import CodeSandboxPlugin
    from runtime.tools.executor import ToolExecutor
    from runtime.tools.search import WebSearchPlugin
    from runtime.usage.observer import RuntimeObserver
    from runtime.usage.token_tracker import TokenTracker

    assert RuntimeAgent is not None
    assert ModelCatalog is not None
    assert ModelRegistry is not None
    assert not hasattr(RuntimeAgent(), "router")
    assert OllamaManager is not None
    assert get_profile("ollama") is not None
    assert PermissionManager is not None
    assert get_elfie_home() is not None
    assert CodeSandboxPlugin is not None
    assert ToolExecutor is not None
    assert WebSearchPlugin is not None
    assert RuntimeObserver is not None
    assert TokenTracker is not None


def test_legacy_runtime_entrypoints_are_removed():
    import importlib.util

    legacy_modules = [
        "runtime.agent",
        "runtime.data_home",
        "runtime.migration",
        "runtime.model_catalog",
        "runtime.model_registry",
        "runtime.model_route",
        "runtime.model_router",
        "runtime.ollama_manager",
        "runtime.permission_manager",
        "runtime.provider_profiles",
        "runtime.scene_classifier",
        "runtime.setup_runtime",
        "runtime.token_tracker",
        "runtime.plugins",
    ]

    for module_name in legacy_modules:
        assert importlib.util.find_spec(module_name) is None
