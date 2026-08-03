"""Contract tests for the first-run Setup model catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.features.setup.model_catalog import (
    SETUP_MODEL_CATALOG,
    get_setup_model,
    setup_model_options,
)
from app.interfaces.api.setup_models import (
    SetupConfigStep,
    SetupInstallPhase,
    SetupModelRequest,
)


def test_setup_model_catalog_is_fixed_and_ordered() -> None:
    assert tuple(option.model_id for option in setup_model_options()) == (
        "qwen2.5:0.5b",
        "qwen3.5:0.8b",
        "gemma3:270m",
    )
    assert tuple(option.label for option in SETUP_MODEL_CATALOG) == (
        "qwen2.5:0.5b（推荐）",
        "qwen3.5:0.8b",
        "gemma3:270m",
    )
    assert tuple(option.recommended for option in SETUP_MODEL_CATALOG) == (
        True,
        False,
        False,
    )
    assert tuple(option.approx_download_mb for option in SETUP_MODEL_CATALOG) == (
        398,
        1024,
        292,
    )


def test_setup_model_catalog_rejects_arbitrary_provider_reference() -> None:
    with pytest.raises(ValueError):
        get_setup_model("ollama/qwen2.5:7b")
    with pytest.raises(ValueError):
        get_setup_model("openai/gpt-5")


def test_setup_model_request_accepts_only_bare_catalog_ids() -> None:
    for model_id in ("qwen2.5:0.5b", "qwen3.5:0.8b", "gemma3:270m"):
        request = SetupModelRequest(decision="configured", model_reference=model_id)
        assert request.model_reference == model_id

    for model_reference in ("ollama/qwen2.5:0.5b", "qwen2.5:7b", "openai/gpt-5"):
        with pytest.raises(ValidationError):
            SetupModelRequest(decision="configured", model_reference=model_reference)


def test_setup_workflow_uses_separate_config_and_install_phase_contracts() -> None:
    assert set(SetupConfigStep.__args__) == {"owner", "offline", "nest", "review"}
    assert set(SetupInstallPhase.__args__) == {
        "owner",
        "ollama",
        "model",
        "emergency_food",
        "nest",
    }
