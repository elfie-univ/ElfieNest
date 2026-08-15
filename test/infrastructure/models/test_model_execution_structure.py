from test.support.model_execution_agent import model_execution_agent_ports


def test_target_runtime_imports_are_available():
    from infrastructure.models.catalog import ModelCatalog
    from infrastructure.models.inference.token_usage import TokenTracker
    from infrastructure.models.model_execution_agent import ModelExecutionAgent
    from infrastructure.models.model_execution_observations import (
        ModelExecutionObserver,
    )
    from infrastructure.models.providers.ollama import OllamaManager
    from infrastructure.models.providers.profiles import get_profile
    from infrastructure.persistence.layout.data_home import get_elfie_home
    from infrastructure.persistence.provider_catalog import load_provider_catalog
    from infrastructure.tools.execution.executor import ToolExecutor
    from infrastructure.tools.execution.permissions import PermissionManager

    assert ModelExecutionAgent is not None
    assert ModelCatalog is not None
    assert not hasattr(
        ModelExecutionAgent(ports=model_execution_agent_ports()), "router"
    )
    assert OllamaManager is not None
    assert get_profile("ollama", catalog=load_provider_catalog()) is not None
    assert PermissionManager is not None
    assert get_elfie_home() is not None
    assert ToolExecutor is not None
    assert ModelExecutionObserver is not None
    assert TokenTracker is not None


def test_legacy_runtime_entrypoints_are_removed():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    assert not (project_root / "ai_runtime").exists()
