"""Machine gates for the frozen AI Runtime design contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_RUNTIME = PROJECT_ROOT / "ai_runtime"
API = PROJECT_ROOT / "app" / "interfaces" / "api"


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_frozen_ai_runtime_contract_hashes_are_unchanged() -> None:
    expected = {
        "docs/developer/architecture-ai-runtime.md": (
            "f668a206a558436edc097589f23ac466a69c7296667016f08ebced759deb9045"
        ),
        "docs/zh/developer/architecture-ai-runtime.md": (
            "2db55ae541e3d4a25c3b9d1aafdddeb73f19dfc8d473b71ad2f93f9eff36f321"
        ),
    }
    for relative_path, digest in expected.items():
        payload = (PROJECT_ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest


def test_legacy_provider_and_model_owner_routes_are_removed() -> None:
    removed = {
        "model_owner_routes.py",
        "provider_config_routes.py",
        "provider_model_routes.py",
        "provider_support.py",
        "provider_validation_routes.py",
    }
    assert not any((API / name).exists() for name in removed)

    app_source = _source("app/interfaces/api/app.py")
    assert "model_owner_routes" not in app_source
    provider_source = _source("app/interfaces/api/provider_routes.py")
    assert "provider_connection_routes" in provider_source
    assert "provider_connection_model_routes" in provider_source


def test_product_runtime_has_one_food_resolver_and_no_direct_model_route() -> None:
    source = _source("ai_runtime/gateway/agent.py")
    assert "ModelRegistry" not in source
    assert "ensure_model_ready" not in source
    assert "def generate_stream(" not in source
    assert "def run_with_food(" in source
    assert "def generate_structured(" in source
    assert not (AI_RUNTIME / "models" / "registry.py").exists()

    setup_source = _source("ai_runtime/setup/runtime_setup.py")
    assert "write_runtime_config" not in setup_source
    assert "cheap_model" not in setup_source
    assert "deep_model" not in setup_source
    assert "multimodal_model" not in setup_source

    config_source = _source("ai_runtime/config.py")
    for legacy_field in (
        "cheap_model",
        "cheap_provider",
        "deep_model",
        "deep_provider",
        "multimodal_model",
        "multimodal_provider",
        "ollama_model_fast",
        "ollama_model_vision",
    ):
        assert legacy_field not in config_source


def test_phase_one_tool_advertising_is_limited_to_safe_tools() -> None:
    prompt_source = _source("ai_runtime/gateway/skills_prompt.py")
    streaming_source = _source("ai_runtime/gateway/streaming.py")
    for forbidden in ("[CODE]", "[SKILL_CREATE]", "[SKILL_MODIFY]"):
        assert forbidden not in prompt_source
        assert forbidden not in streaming_source
    assert "[SEARCH]" in prompt_source
    assert "[READ_FILE]" in prompt_source


def test_reports_and_food_facts_use_only_contract_paths() -> None:
    data_home_source = _source("ai_runtime/storage/data_home.py")
    assert "ai-runtime.sqlite" in data_home_source
    assert "runtime_events.jsonl" not in _source("ai_runtime/usage/observer.py")

    forbidden_names = {
        "model-evidence.yaml",
        "food_policy.yaml",
        "runtime_events.jsonl",
    }
    product_sources = [
        *AI_RUNTIME.rglob("*.py"),
        *(PROJECT_ROOT / "app").rglob("*.py"),
    ]
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in product_sources
        if any(name in path.read_text(encoding="utf-8") for name in forbidden_names)
    }
    assert offenders == set()
