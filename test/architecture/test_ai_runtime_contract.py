"""Machine gates for the temporary model, Food and tool behavior contract."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_RUNTIME = PROJECT_ROOT / "ai_runtime"
API = PROJECT_ROOT / "app" / "interfaces" / "api"


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_model_food_tool_contract_defers_target_ownership_to_system() -> None:
    english = _source("docs/developer/contracts/ai-runtime.md")
    chinese = _source("docs/zh/developer/contracts/ai-runtime.md")

    assert "**Contract version:** 1.5" in english
    assert "**契约版本：** 1.5" in chinese
    assert "does not define a target AI Runtime module" in english
    assert "不定义目标 AI Runtime 模块" in chinese
    assert "infrastructure/ai_runtime" not in english
    assert "infrastructure/ai_runtime" not in chinese


def test_food_model_contract_keeps_independent_ports_and_semantic_authority() -> None:
    english = _source("docs/developer/contracts/ai-runtime.md")
    chinese = _source("docs/zh/developer/contracts/ai-runtime.md")

    assert 'EL["Elfie cognition"] --> FPOR["Elfie FoodPort"]' in english
    assert 'EL --> MPOR["Elfie ModelPort"]' in english
    assert "FPOR --> GW" not in english
    assert "nest.db` remains the authority" not in english
    assert "不重新作出授权决策" in chinese
    assert "物理持久化存储" in chinese
    assert "语义 authority" in chinese


def test_behavior_contract_keeps_fallback_and_tool_scope_narrow() -> None:
    english = _source("docs/developer/contracts/ai-runtime.md")
    chinese = _source("docs/zh/developer/contracts/ai-runtime.md")

    assert "one optional `fallback` model" in english
    assert "一个可选的 `fallback` 模型" in chinese
    assert "semantic resource identifiers, not an arbitrary filesystem root" in english
    assert "语义资源标识，不携带任意文件系统根目录" in chinese
    assert "requires a separate approved contract" in english
    assert "必须先有单独获批的" in chinese


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

    assert not (AI_RUNTIME / "storage" / "runtime_config_bundle.py").exists()
    product_sources = [
        *AI_RUNTIME.rglob("*.py"),
        *(PROJECT_ROOT / "app").rglob("*.py"),
    ]
    old_symbols = {
        "ModelEvidenceStore",
        "read_runtime_config_bundle",
        "write_runtime_config_bundle",
    }
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in product_sources
        if any(symbol in path.read_text(encoding="utf-8") for symbol in old_symbols)
    }
    assert offenders == set()


def test_model_consumers_share_the_sqlite_evidence_projection() -> None:
    consumers = {
        "ai_runtime/gateway/agent.py",
        "ai_runtime/lab/cli.py",
        "ai_runtime/validation/overview.py",
        "app/features/configuration/food_access.py",
        "app/features/setup/ollama.py",
        "app/interfaces/api/food_catalog_support.py",
        "app/interfaces/api/provider_model_matrix.py",
    }
    assert all("query_model_evidence" in _source(path) for path in consumers)
    evidence_source = _source("ai_runtime/food/evidence.py")
    assert "ProviderConnectionStore" in evidence_source
    assert "ReportRepository" in evidence_source
    assert "read_yaml" not in evidence_source


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


def test_provider_catalogs_do_not_encode_runtime_model_selection_groups() -> None:
    catalog_sources = (
        "ai_runtime/providers/catalog.py",
        "ai_runtime/providers/remote_catalog.py",
        "app/interfaces/api/provider_connection_routes.py",
    )
    forbidden_groups = ("cheap", "deep", "multimodal")
    for source_path in catalog_sources:
        source = _source(source_path)
        assert all(group not in source for group in forbidden_groups)


def test_phase_one_tool_advertising_is_limited_to_safe_tools() -> None:
    prompt_source = _source("ai_runtime/gateway/skills_prompt.py")
    streaming_source = _source("ai_runtime/gateway/streaming.py")
    for forbidden in ("[CODE]", "[SKILL_CREATE]", "[SKILL_MODIFY]"):
        assert forbidden not in prompt_source
        assert forbidden not in streaming_source
    assert "[SEARCH]" in prompt_source
    assert "[READ_FILE]" in prompt_source
    config_source = _source("ai_runtime/tools/config.py")
    assert '"web_search"' in config_source
    assert '"local_file"' in config_source
    assert '"code_sandbox"' not in config_source
    for source_path in (
        "ai_runtime/gateway/agent.py",
        "ai_runtime/food/executor.py",
    ):
        source = _source(source_path)
        assert "CodeSandboxPlugin" not in source
        assert "SkillsSelfEvolutionPlugin" not in source


def test_reports_and_food_facts_use_only_contract_paths() -> None:
    data_home_source = _source("ai_runtime/storage/data_home.py")
    assert "ai-runtime.sqlite" in data_home_source
    assert "runtime_events.jsonl" not in _source("ai_runtime/usage/observer.py")

    forbidden_names = {
        "model-evidence.yaml",
        "model_evidence.yaml",
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


def test_elfie_main_food_uses_the_final_elfie_row_without_legacy_policy() -> None:
    schema_source = _source("app/infrastructure/persistence/final_schema.py")
    assert "main_food_id TEXT" in schema_source
    assert "elfie_food_preferences" not in schema_source

    legacy_food_symbols = (
        "ElfieFoodPolicy",
        "FIXED_FOOD_KINDS",
        "allowed_foods",
        "def default_food(",
        "def fallback_food(",
    )
    product_sources = [
        *AI_RUNTIME.rglob("*.py"),
        *(PROJECT_ROOT / "app").rglob("*.py"),
    ]
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in product_sources
        if any(
            symbol in path.read_text(encoding="utf-8") for symbol in legacy_food_symbols
        )
    }
    assert offenders == set()
