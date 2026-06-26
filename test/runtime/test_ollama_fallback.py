import json
from unittest.mock import Mock, patch

from runtime.models.local_profiles import select_local_profile
from runtime.providers.ollama import OllamaManager
from runtime.setup.runtime_setup import MODELS_TO_PULL


def test_select_local_profile_by_memory_size():
    assert select_local_profile(4).text_model == "qwen2.5:0.5b"
    assert select_local_profile(8).text_model == "qwen3.5:0.8b"
    assert select_local_profile(16).text_model == "qwen2.5:3b"
    assert select_local_profile(32).text_model == "qwen2.5:7b"


def test_setup_models_to_pull_use_local_fallback_profile():
    profile = select_local_profile(8)

    assert MODELS_TO_PULL == [profile.text_model, profile.vision_model]


def test_ollama_manager_lists_installed_models():
    manager = OllamaManager(Mock(ollama_host="http://localhost:11434"))
    response = Mock()
    response.read.return_value = json.dumps(
        {"models": [{"name": "qwen3.5:0.8b"}, {"name": "moondream:latest"}]}
    ).encode("utf-8")
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch("urllib.request.urlopen", return_value=response):
        assert manager.list_installed_models() == ("qwen3.5:0.8b", "moondream:latest")


def test_ollama_manager_checks_model_presence():
    manager = OllamaManager(Mock(ollama_host="http://localhost:11434"))

    with patch.object(
        manager,
        "list_installed_models",
        return_value=("qwen3.5:0.8b", "moondream:latest"),
    ):
        assert manager.has_model("qwen3.5:0.8b") is True
        assert manager.has_model("moondream") is True
        assert manager.has_model("llama3") is False
