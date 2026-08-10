from unittest.mock import Mock

from app.features.configuration.providers import (
    StoredLocalProviderBinding,
    StoredLocalProviderProbe,
)
from infrastructure.models import OllamaLifecycleAdapter


def test_lifecycle_ollama_only_starts_an_unhealthy_existing_binding() -> None:
    technology = Mock()
    binding = StoredLocalProviderBinding(
        api_base="http://localhost:11434",
        platform="darwin",
        install_kind="existing-public",
        launch_target="/Applications/Ollama.app",
    )
    technology.default_binding.return_value = binding
    technology.probe.side_effect = (
        StoredLocalProviderProbe("unavailable", binding.api_base),
        StoredLocalProviderProbe("unavailable", binding.api_base),
    )
    adapter = OllamaLifecycleAdapter(technology)

    assert adapter.ready() is False
    adapter.prepare()

    technology.start.assert_called_once_with(binding)
