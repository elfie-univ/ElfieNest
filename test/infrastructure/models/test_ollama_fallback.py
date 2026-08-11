import json
from unittest.mock import Mock, patch

import pytest

from ai_runtime.setup.runtime_setup import MODELS_TO_PULL
from infrastructure.models.local_profiles import (
    recommend_local_profile,
    select_local_profile,
)
from infrastructure.models.providers.ollama import OllamaManager, OllamaNotReadyError


def test_select_local_profile_by_memory_size():
    assert select_local_profile(4).text_model == "qwen2.5:0.5b"
    assert select_local_profile(8).text_model == "qwen3.5:0.8b"
    assert select_local_profile(16).text_model == "qwen2.5:3b"
    assert select_local_profile(32).text_model == "qwen2.5:7b"


def test_local_model_recommendation_requires_at_least_four_gb():
    assert recommend_local_profile(3) is None
    assert recommend_local_profile(4).text_model == "qwen2.5:0.5b"


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


def test_supervised_runtime_never_starts_ollama_process(monkeypatch):
    """桌面 supervisor 托管时，Core 只能检查 Ollama，不能重复 Popen。"""
    manager = OllamaManager(Mock(ollama_host="http://localhost:11434"))
    monkeypatch.setenv("ELFIENEST_SUPERVISED", "1")

    with (
        patch.object(manager, "check_health", return_value=False),
        patch("infrastructure.models.providers.ollama.subprocess.Popen") as popen,
    ):
        with pytest.raises(OllamaNotReadyError, match="supervisor"):
            manager.ensure_service_started()

    popen.assert_not_called()


def test_ollama_manager_never_looks_for_a_project_private_binary():
    """Ollama is a user-managed public service, not a runtime sidecar."""
    manager = OllamaManager(Mock(ollama_host="http://localhost:11434"))

    assert not hasattr(manager, "ollama_path")


def test_ollama_manager_starts_only_the_recorded_public_binding():
    config = Mock(
        ollama_host="http://127.0.0.1:11434",
        providers={
            "ollama": {
                "installation": {
                    "platform": "linux",
                    "install_kind": "binary",
                    "launch_target": "/usr/local/bin/ollama",
                }
            }
        },
    )
    manager = OllamaManager(config)

    with (
        patch.object(manager, "check_health", side_effect=[False, True]),
        patch("infrastructure.models.providers.ollama.subprocess.Popen") as popen,
    ):
        assert manager.ensure_service_started() is True

    popen.assert_called_once()
    assert popen.call_args.args[0] == ["/usr/local/bin/ollama", "serve"]


def test_ollama_manager_refuses_to_scan_path_when_no_binding_is_recorded():
    manager = OllamaManager(Mock(ollama_host="http://127.0.0.1:11434", providers={}))

    with (
        patch.object(manager, "check_health", return_value=False),
        patch("infrastructure.models.providers.ollama.subprocess.Popen") as popen,
    ):
        with pytest.raises(OllamaNotReadyError, match="固定绑定"):
            manager.ensure_service_started()

    popen.assert_not_called()
