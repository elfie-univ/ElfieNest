def test_layered_runtime_imports_are_available():
    from ai_runtime.gateway.agent import RuntimeAgent
    from ai_runtime.models.catalog import ModelCatalog
    from ai_runtime.providers.ollama import OllamaManager
    from ai_runtime.providers.profiles import get_profile
    from ai_runtime.safety.permissions import PermissionManager
    from ai_runtime.tools.executor import ToolExecutor
    from ai_runtime.tools.search import WebSearchPlugin
    from ai_runtime.usage.observer import RuntimeObserver
    from ai_runtime.usage.token_tracker import TokenTracker
    from infrastructure.persistence.data_home import get_elfie_home

    assert RuntimeAgent is not None
    assert ModelCatalog is not None
    assert not hasattr(RuntimeAgent(), "router")
    assert OllamaManager is not None
    assert get_profile("ollama") is not None
    assert PermissionManager is not None
    assert get_elfie_home() is not None
    assert ToolExecutor is not None
    assert WebSearchPlugin is not None
    assert RuntimeObserver is not None
    assert TokenTracker is not None


def test_legacy_runtime_entrypoints_are_removed():
    import importlib.util

    legacy_modules = [
        "ai_runtime.agent",
        "ai_runtime.data_home",
        "ai_runtime.migration",
        "ai_runtime.model_catalog",
        "ai_runtime.model_registry",
        "ai_runtime.model_route",
        "ai_runtime.model_router",
        "ai_runtime.ollama_manager",
        "ai_runtime.permission_manager",
        "ai_runtime.provider_profiles",
        "ai_runtime.scene_classifier",
        "ai_runtime.setup_runtime",
        "ai_runtime.token_tracker",
        "ai_runtime.plugins",
    ]

    for module_name in legacy_modules:
        assert importlib.util.find_spec(module_name) is None
