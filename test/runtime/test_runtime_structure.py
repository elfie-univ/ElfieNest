def test_gateway_agent_imports_match_legacy_path():
    from runtime.agent import RuntimeAgent as LegacyRuntimeAgent
    from runtime.gateway.agent import RuntimeAgent

    assert RuntimeAgent is LegacyRuntimeAgent


def test_layered_runtime_imports_are_available():
    from runtime.models.catalog import ModelCatalog
    from runtime.models.registry import ModelRegistry
    from runtime.policy.router import ModelRouter
    from runtime.providers.ollama import OllamaManager
    from runtime.providers.profiles import get_profile
    from runtime.safety.permissions import PermissionManager
    from runtime.storage.data_home import get_elfie_home
    from runtime.tools.code import CodeSandboxPlugin
    from runtime.tools.executor import ToolExecutor
    from runtime.tools.search import WebSearchPlugin
    from runtime.usage.observer import RuntimeObserver
    from runtime.usage.token_tracker import TokenTracker

    assert ModelCatalog is not None
    assert ModelRegistry is not None
    assert ModelRouter is not None
    assert OllamaManager is not None
    assert get_profile("ollama") is not None
    assert PermissionManager is not None
    assert get_elfie_home() is not None
    assert CodeSandboxPlugin is not None
    assert ToolExecutor is not None
    assert WebSearchPlugin is not None
    assert RuntimeObserver is not None
    assert TokenTracker is not None


def test_legacy_setup_runtime_entrypoint_exposes_main():
    from runtime.setup.runtime_setup import main as LayeredMain
    from runtime.setup_runtime import main as LegacyMain

    assert LegacyMain is LayeredMain
