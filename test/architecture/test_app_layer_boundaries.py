"""Machine gates for the versioned App architecture contract."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Set, Tuple

from fastapi.routing import APIRoute

from app.interfaces.api import create_app
from scripts.architecture.app_layer_scan import (
    APP_ROOT,
    LOOSE_OUTPUT_TYPES,
    RULE_LEDGER_IDS,
    _annotation_names,
    _cycles,
    _feature_dependency_graph,
    _has_strict_response_model,
    _imported_modules,
    _is_non_json_handler,
    _python_files,
    _relative,
    _route_decorators,
    _tree,
    collect_app_layer_violations,
    deny_all_failures,
)
from scripts.architecture.check_governance_change import classify_paths
from test.architecture.baselines.app_layer import LEGACY_APP_LAYER_VIOLATIONS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_app_legacy_baseline_exactly_matches_current_debt() -> None:
    current = collect_app_layer_violations()
    assert set(LEGACY_APP_LAYER_VIOLATIONS) == set(RULE_LEDGER_IDS)
    assert current == LEGACY_APP_LAYER_VIOLATIONS


def test_app_deny_all_accepts_zero_and_rejects_any_violation() -> None:
    empty = {rule: frozenset() for rule in RULE_LEDGER_IDS}
    assert deny_all_failures(empty) == []
    assert deny_all_failures({"rule": frozenset({"path -> dependency"})}) == [
        "rule: violations are forbidden in deny-all mode: ['path -> dependency']"
    ]


def test_app_feature_dependency_graph_is_acyclic() -> None:
    assert _cycles(_feature_dependency_graph(APP_ROOT / "features")) == set()


def test_new_port_and_model_modules_cannot_use_any() -> None:
    offenders: Set[str] = set()
    for root in (APP_ROOT / "features", APP_ROOT / "orchestration"):
        for path in _python_files(root):
            if path.name not in {"models.py", "ports.py"}:
                continue
            names = {
                node.id for node in ast.walk(_tree(path)) if isinstance(node, ast.Name)
            }
            if "Any" in names:
                offenders.add(_relative(path))
    assert offenders == set()


def test_registered_api_routes_do_not_duplicate_method_and_path() -> None:
    application = create_app(db_path=":memory:")
    owners: DefaultDict[Tuple[str, str], List[str]] = defaultdict(list)
    for route in application.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            owners[(method, route.path)].append(route.name)
    duplicates = {key: names for key, names in owners.items() if len(names) > 1}
    assert duplicates == {}


def test_app_boundary_scanner_catches_relative_import_fixture(tmp_path: Path) -> None:
    feature = tmp_path / "app" / "features" / "sample"
    feature.mkdir(parents=True)
    source = feature / "service.py"
    source.write_text(
        "from ...infrastructure.persistence.store import get_db\n",
        encoding="utf-8",
    )
    assert "app.infrastructure.persistence.store" in _imported_modules(source)


def test_route_scanner_distinguishes_json_and_response_fixtures(
    tmp_path: Path,
) -> None:
    api = tmp_path / "app" / "interfaces" / "api"
    api.mkdir(parents=True)
    source = api / "routes.py"
    source.write_text(
        "from typing import Any, Dict\n"
        "from fastapi import APIRouter\n"
        "from fastapi.responses import Response\n"
        "router = APIRouter()\n"
        "@router.get('/loose')\n"
        "def loose() -> Dict[str, Any]: return {}\n"
        "@router.get('/page')\n"
        "def page() -> Response: return Response()\n",
        encoding="utf-8",
    )
    violations: DefaultDict[str, Set[str]] = defaultdict(set)
    _scan_api_route_models_for_fixture(source, violations)
    missing = violations["json_routes_missing_response_model"]
    assert any("GET /loose" in entry for entry in missing)
    assert all("GET /page" not in entry for entry in missing)
    assert any(
        "GET /loose::return:loose" in entry
        for entry in violations["json_routes_loose_annotations"]
    )


def _scan_api_route_models_for_fixture(
    path: Path,
    violations: DefaultDict[str, Set[str]],
) -> None:
    for node in ast.walk(_tree(path)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = list(_route_decorators(node))
        if not decorators or _is_non_json_handler(node):
            continue
        for method, route, decorator in decorators:
            location = f"{path.name}::{node.name}::{method} {route}"
            if not _has_strict_response_model(decorator):
                violations["json_routes_missing_response_model"].add(location)
            if node.returns is not None and (
                _annotation_names(node.returns) & LOOSE_OUTPUT_TYPES
            ):
                violations["json_routes_loose_annotations"].add(
                    f"{location}::return:loose"
                )


def test_application_contract_and_ledger_have_bilingual_authority_markers() -> None:
    english_contract = (
        PROJECT_ROOT / "docs/developer/contracts/application.md"
    ).read_text(encoding="utf-8")
    chinese_contract = (
        PROJECT_ROOT / "docs/zh/developer/contracts/application.md"
    ).read_text(encoding="utf-8")
    english_ledger = (
        PROJECT_ROOT / "docs/developer/conformance/application.md"
    ).read_text(encoding="utf-8")
    chinese_ledger = (
        PROJECT_ROOT / "docs/zh/developer/conformance/application.md"
    ).read_text(encoding="utf-8")

    assert "**Contract version:** 1.4" in english_contract
    assert "**契约版本：** 1.4" in chinese_contract
    assert "test_app_layer_boundaries.py" in english_contract
    assert "test_app_layer_boundaries.py" in chinese_contract
    for number in range(1, 13):
        gap_id = f"APP-{number:03d}"
        assert gap_id in english_ledger
        assert gap_id in chinese_ledger


def test_architecture_governance_layout_and_local_rules_exist() -> None:
    required_docs = {
        "docs/developer/architecture/index.md",
        "docs/developer/contracts/application.md",
        "docs/developer/contracts/repository-governance.md",
        "docs/developer/conformance/application.md",
        "docs/developer/decisions/0001-lightweight-ports-adapters.md",
        "docs/zh/developer/architecture/index.md",
        "docs/zh/developer/contracts/application.md",
        "docs/zh/developer/contracts/repository-governance.md",
        "docs/zh/developer/conformance/application.md",
        "docs/zh/developer/decisions/0001-lightweight-ports-adapters.md",
    }
    required_agents = {
        "app/AGENTS.md",
        "app/features/AGENTS.md",
        "app/features/accounts/AGENTS.md",
        "app/features/administration/AGENTS.md",
        "app/features/configuration/AGENTS.md",
        "app/orchestration/AGENTS.md",
        "app/bootstrap/AGENTS.md",
        "app/infrastructure/AGENTS.md",
        "app/interfaces/AGENTS.md",
        "app/orchestration/lifecycle/AGENTS.md",
        "app/orchestration/embodiment/AGENTS.md",
        "app/infrastructure/devices/AGENTS.md",
        "app/interfaces/api/AGENTS.md",
        "app/interfaces/desktop/AGENTS.md",
        "app/interfaces/cli/AGENTS.md",
        "app/features/setup/AGENTS.md",
        "test/architecture/AGENTS.md",
        "scripts/architecture/AGENTS.md",
    }
    assert all((PROJECT_ROOT / path).is_file() for path in required_docs)
    assert all((PROJECT_ROOT / path).is_file() for path in required_agents)


def test_governance_change_classifier_rejects_self_approval_mix() -> None:
    governance, production = classify_paths(
        {
            "docs/developer/contracts/application.md",
            "scripts/architecture/app_layer_scan.py",
            "app/features/adoption/service.py",
        }
    )
    assert governance == {
        "docs/developer/contracts/application.md",
        "scripts/architecture/app_layer_scan.py",
    }
    assert production == {"app/features/adoption/service.py"}


def test_baseline_reduction_is_not_classified_as_governance() -> None:
    governance, production = classify_paths(
        {
            "test/architecture/baselines/app_layer.py",
            "app/features/adoption/service.py",
        }
    )
    assert governance == set()
    assert production == {"app/features/adoption/service.py"}


def test_all_architecture_tests_except_baselines_are_governance() -> None:
    governance, production = classify_paths(
        {
            "test/architecture/test_storage_boundaries.py",
            "test/architecture/baselines/app_layer.py",
        }
    )
    assert governance == {"test/architecture/test_storage_boundaries.py"}
    assert production == set()
