from dataclasses import dataclass
from typing import Any

import pytest

from ai_runtime.gateway.model_guard import UnsupportedModalError, ensure_model_ready


@dataclass
class FakeRegistry:
    model_info: dict[str, Any]

    def get_model_info(self, model_key: str) -> dict[str, Any]:
        return self.model_info


@dataclass
class FakeOllamaManager:
    started: bool = False

    def ensure_service_started(self) -> bool:
        self.started = True
        return True


def test_ensure_model_ready_returns_target_and_starts_ollama():
    registry = FakeRegistry(
        {
            "name": "qwen3.5:0.8b",
            "provider": "ollama",
            "is_vision": False,
            "is_audio": False,
            "active": True,
        }
    )
    ollama_manager = FakeOllamaManager()

    target = ensure_model_ready("local_fast", registry, ollama_manager)

    assert target.model_name == "qwen3.5:0.8b"
    assert target.provider == "ollama"
    assert ollama_manager.started is True


def test_ensure_model_ready_rejects_inactive_model():
    registry = FakeRegistry(
        {
            "name": "remote",
            "provider": "openai",
            "is_vision": False,
            "is_audio": False,
            "active": False,
        }
    )

    with pytest.raises(ValueError):
        ensure_model_ready("remote_deep", registry, FakeOllamaManager())


def test_ensure_model_ready_rejects_unsupported_image_input():
    registry = FakeRegistry(
        {
            "name": "remote",
            "provider": "openai",
            "is_vision": False,
            "is_audio": False,
            "active": True,
        }
    )

    with pytest.raises(UnsupportedModalError):
        ensure_model_ready(
            "remote_deep", registry, FakeOllamaManager(), images=["a.jpg"]
        )
