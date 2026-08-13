"""Machine gates for the model, Food and tool behavior contract."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RETIRED_RUNTIME_ROOT = PROJECT_ROOT / "ai_runtime"
LEGACY_CONTRACT_PATHS = (
    PROJECT_ROOT / "docs/developer/contracts/ai-runtime.md",
    PROJECT_ROOT / "docs/zh/developer/contracts/ai-runtime.md",
    PROJECT_ROOT / "docs/developer/conformance/ai-runtime.md",
    PROJECT_ROOT / "docs/zh/developer/conformance/ai-runtime.md",
)
RETIRED_CONFORMANCE_PATHS = (
    PROJECT_ROOT / "docs/developer/conformance/model-food-tool-conformance.md",
    PROJECT_ROOT / "docs/zh/developer/conformance/model-food-tool-conformance.md",
)
API = PROJECT_ROOT / "app" / "interfaces" / "api"


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_model_food_tool_contract_defers_target_ownership_to_system() -> None:
    english = _source("docs/developer/contracts/model-food-tool-behavior.md")
    chinese = _source("docs/zh/developer/contracts/model-food-tool-behavior.md")

    assert all(
        not path.exists()
        for path in (*LEGACY_CONTRACT_PATHS, *RETIRED_CONFORMANCE_PATHS)
    )
    assert "**Contract version:** 1.6" in english
    assert "**契约版本：** 1.6" in chinese
    assert "does not define a target Runtime module" in english
    assert "不定义目标 Runtime 模块" in chinese
    assert "infrastructure/ai_runtime" not in english
    assert "infrastructure/ai_runtime" not in chinese


def test_food_model_contract_keeps_independent_ports_and_semantic_authority() -> None:
    english = _source("docs/developer/contracts/model-food-tool-behavior.md")
    chinese = _source("docs/zh/developer/contracts/model-food-tool-behavior.md")

    assert 'EL["Elfie cognition"] --> FPOR["Elfie FoodPort"]' in english
    assert 'EL --> MPOR["Elfie ModelPort"]' in english
    assert "FPOR --> GW" not in english
    assert "nest.db` remains the authority" not in english
    assert "不重新作出授权决策" in chinese
    assert "物理持久化存储" in chinese
    assert "语义 authority" in chinese


def test_behavior_contract_keeps_fallback_and_tool_scope_narrow() -> None:
    english = _source("docs/developer/contracts/model-food-tool-behavior.md")
    chinese = _source("docs/zh/developer/contracts/model-food-tool-behavior.md")

    assert "one optional `fallback` model" in english
    assert "一个可选的 `fallback` 模型" in chinese
    assert "semantic resource identifiers, not an arbitrary filesystem root" in english
    assert "语义资源标识，不携带任意文件系统根目录" in chinese
    assert "requires a separate approved contract" in english
    assert "必须先有单独获批的" in chinese


def test_legacy_provider_and_model_owner_routes_are_removed() -> None:
    removed = {
        "model_owner_routes.py",
        "ollama_owner_routes.py",
        "provider_config_routes.py",
        "provider_model_routes.py",
        "provider_routes.py",
        "provider_support.py",
        "provider_validation_routes.py",
    }
    assert not any((API / name).exists() for name in removed)

    app_source = _source("app/interfaces/api/app.py")
    assert "model_owner_routes" not in app_source
    versioned_source = _source("app/interfaces/api/v1/admin/model_providers/routes.py")
    assert 'prefix="/api/v1/admin/model-providers"' in versioned_source
    assert '"/model-matrix"' in versioned_source
    assert '"/model-benchmarks"' in versioned_source
    assert '"/model-validations"' in versioned_source

    assert not (RETIRED_RUNTIME_ROOT / "storage" / "runtime_config_bundle.py").exists()
    product_sources = [
        *(PROJECT_ROOT / "app").rglob("*.py"),
        *(PROJECT_ROOT / "infrastructure").rglob("*.py"),
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
    # Model capabilities consume semantic evidence through Ports.  The sole
    # SQLite implementation belongs to persistence and is composed by
    # Bootstrap/devtools; model code must not reach into either repository.
    execution_source = _source("infrastructure/models/model_execution_agent.py")
    overview_source = _source("infrastructure/models/model_execution_overview.py")
    food_source = _source("infrastructure/models/food_technology.py")
    matrix_source = _source("infrastructure/models/validation/provider_model_matrix.py")
    assert "model_evidence_source" in execution_source
    assert "self.evidence" in overview_source
    assert "FoodEvidencePort" in food_source
    assert "provider_validation_reader" in matrix_source
    assert "ProviderConnectionStore" not in food_source
    assert "ReportRepository" not in food_source
    assert "read_yaml" not in food_source
    persistence_source = _source("infrastructure/persistence/food_evidence.py")
    assert "ProviderConnectionStore" in persistence_source
    assert "ReportRepository" in persistence_source


def test_product_runtime_has_one_food_resolver_and_no_direct_model_route() -> None:
    source = _source("infrastructure/models/model_execution_agent.py")
    assert "ModelRegistry" not in source
    assert "ensure_model_ready" not in source
    assert "def generate_stream(" not in source
    assert "def run_with_food(" in source
    assert "def generate_structured(" in source
    assert not (RETIRED_RUNTIME_ROOT / "models" / "registry.py").exists()

    assert not (RETIRED_RUNTIME_ROOT / "setup").exists()
    assert not (RETIRED_RUNTIME_ROOT / "policy").exists()

    config_source = _source("infrastructure/models/model_execution_config.py")
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
        "infrastructure/models/providers/catalog.py",
        "infrastructure/models/providers/remote_catalog.py",
        "infrastructure/models/provider_administration.py",
    )
    forbidden_groups = ("cheap", "deep", "multimodal")
    for source_path in catalog_sources:
        source = _source(source_path)
        assert all(group not in source for group in forbidden_groups)
        assert not any((RETIRED_RUNTIME_ROOT / "models").rglob("*.py"))
        assert not any((RETIRED_RUNTIME_ROOT / "providers").rglob("*.py"))


def test_phase_one_tool_advertising_is_limited_to_safe_tools() -> None:
    prompt_source = _source("infrastructure/tools/execution/skills_prompt.py")
    for forbidden in ("[CODE]", "[SKILL_CREATE]", "[SKILL_MODIFY]"):
        assert forbidden not in prompt_source
        assert forbidden not in _source("infrastructure/models/inference/llm_api.py")
    assert "[SEARCH]" in prompt_source
    assert "[READ_FILE]" in prompt_source
    config_source = _source("infrastructure/tools/execution/config.py")
    assert '"web_search"' in config_source
    assert '"local_file"' in config_source
    for legacy_gateway_leaf in (
        "llm_api.py",
        "model_guard.py",
        "multimodal.py",
        "streaming.py",
    ):
        assert not (RETIRED_RUNTIME_ROOT / "gateway" / legacy_gateway_leaf).exists()
    assert not (PROJECT_ROOT / "infrastructure/models/inference/streaming.py").exists()
    assert '"code_sandbox"' not in config_source
    for source_path in (
        "infrastructure/models/model_execution_agent.py",
        "infrastructure/models/food_execution.py",
    ):
        source = _source(source_path)
        assert "CodeSandboxPlugin" not in source
        assert "SkillsSelfEvolutionPlugin" not in source


def test_model_execution_uses_bootstrap_ports_for_technical_capabilities() -> None:
    """Keep ModelExecutionAgent behavior in Models while wiring Tools at Bootstrap."""
    execution_path = PROJECT_ROOT / "infrastructure/models/model_execution_agent.py"
    tree = ast.parse(execution_path.read_text(encoding="utf-8"))
    execution_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ModelExecutionAgent"
    )
    constructor = next(
        node
        for node in execution_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assert any(argument.arg == "ports" for argument in constructor.args.kwonlyargs)

    concrete_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and (
            node.module == "infrastructure.persistence"
            or node.module.startswith("infrastructure.persistence.")
            or node.module == "infrastructure.tools"
            or node.module.startswith("infrastructure.tools.")
        )
    }
    assert concrete_imports == set()

    wiring_source = _source("app/bootstrap/system_wiring/model_execution.py")
    assert "build_model_execution_agent_ports" in wiring_source
    assert "PermissionManager" in wiring_source
    assert "LocalFileAccessPlugin" in wiring_source
    assert "WebSearchPlugin" in wiring_source


def test_model_and_tool_capabilities_do_not_construct_persistence_adapters() -> None:
    """Infrastructure capabilities stay shallow and receive storage through Ports."""
    offenders: list[str] = []
    for relative_root in ("infrastructure/models", "infrastructure/tools"):
        root = PROJECT_ROOT / relative_root
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module: str | None = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if (
                            alias.name == "infrastructure.persistence"
                            or alias.name.startswith("infrastructure.persistence.")
                        ):
                            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
                if module == "infrastructure.persistence" or (
                    module is not None
                    and module.startswith("infrastructure.persistence.")
                ):
                    offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert offenders == []


def test_platform_adapters_do_not_reach_other_infrastructure_capabilities() -> None:
    """Platform mechanics receive App-owned ports instead of storage/model adapters."""
    offenders: list[str] = []
    root = PROJECT_ROOT / "infrastructure/platform"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(
                        (
                            "infrastructure.models",
                            "infrastructure.persistence",
                            "infrastructure.tools",
                        )
                    ):
                        offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
            if module is not None and module.startswith(
                (
                    "infrastructure.models",
                    "infrastructure.persistence",
                    "infrastructure.tools",
                )
            ):
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert offenders == []


def test_reports_and_food_facts_use_only_contract_paths() -> None:
    data_home_source = _source("infrastructure/persistence/layout/data_home.py")
    assert "ai-runtime.sqlite" in data_home_source
    assert "runtime_events.jsonl" not in _source(
        "infrastructure/models/model_execution_observations.py"
    )

    forbidden_names = {
        "model-evidence.yaml",
        "model_evidence.yaml",
        "food_policy.yaml",
        "runtime_events.jsonl",
    }
    product_sources = [
        *(PROJECT_ROOT / "app").rglob("*.py"),
        *(PROJECT_ROOT / "infrastructure").rglob("*.py"),
    ]
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in product_sources
        if any(name in path.read_text(encoding="utf-8") for name in forbidden_names)
    }
    assert offenders == set()


def test_elfie_main_food_uses_the_final_elfie_row_without_legacy_policy() -> None:
    schema_source = _source("infrastructure/persistence/nest_db/final_schema.py")
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
        *(PROJECT_ROOT / "app").rglob("*.py"),
        *(PROJECT_ROOT / "infrastructure").rglob("*.py"),
    ]
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in product_sources
        if any(
            symbol in path.read_text(encoding="utf-8") for symbol in legacy_food_symbols
        )
    }
    assert offenders == set()
