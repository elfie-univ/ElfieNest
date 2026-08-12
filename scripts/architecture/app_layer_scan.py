"""Reusable scanner for the versioned App architecture contract."""

from __future__ import annotations

import argparse
import ast
import runpy
import sys
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple

from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
APP_LAYERS = frozenset(
    {"bootstrap", "features", "infrastructure", "interfaces", "orchestration"}
)
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
NON_JSON_RESPONSE_TYPES = frozenset(
    {
        "FileResponse",
        "HTMLResponse",
        "PlainTextResponse",
        "RedirectResponse",
        "Response",
        "StreamingResponse",
    }
)
LOOSE_INPUT_TYPES = frozenset({"Any", "Dict", "Mapping", "dict", "object"})
LOOSE_OUTPUT_TYPES = LOOSE_INPUT_TYPES | frozenset({"List", "list"})
ADAPTER_SUFFIXES = ("Repository", "Registry", "Store")
UNOWNED_TASK_CALLS = frozenset({"Process", "Thread", "create_task"})
PUBLIC_UNVERSIONED_HTTP_EXCEPTIONS = frozenset({"/api/health"})
TARGET_FEATURE_DOMAINS = frozenset(
    {
        "accounts",
        "adoption",
        "bodies",
        "communication",
        "configuration",
        "elfies",
        "nest_management",
        "operations",
        "setup",
    }
)
TARGET_CONFIGURATION_DOMAINS = frozenset(
    {"capabilities", "food", "providers", "settings"}
)
TARGET_ORCHESTRATION_DOMAINS = frozenset(
    {
        "embodiment",
        "lifecycle",
        "message_delivery",
        "nest_session",
        "observer",
        "resident_admission",
        "setup_installation",
    }
)
TARGET_API_V1_DOMAINS = frozenset(
    {"admin", "auth", "elfies", "me", "observer", "realtime", "setup"}
)
TARGET_API_ADMIN_DOMAINS = frozenset(
    {
        "elfies",
        "food_packages",
        "model_providers",
        "nest",
        "runtime",
        "settings",
        "users",
    }
)

RULE_NAMES = frozenset(
    {
        "interface_forbidden_layer_imports",
        "feature_forbidden_layer_imports",
        "orchestration_forbidden_layer_imports",
        "infrastructure_forbidden_layer_imports",
        "feature_framework_imports",
        "feature_public_db_path",
        "interface_adapter_construction",
        "cross_feature_internal_imports",
        "interface_feature_internal_imports",
        "interface_orchestration_internal_imports",
        "orchestration_private_boundary_imports",
        "infrastructure_feature_internal_imports",
        "json_routes_missing_response_model",
        "json_routes_loose_annotations",
        "websocket_loose_payloads",
        "nonstandard_error_responses",
        "feature_unowned_task_calls",
        "interface_runtime_lifecycle_calls",
        "unversioned_product_routes",
        "unowned_app_directories",
    }
)


def configure_project_root(project_root: Path) -> None:
    """Point the scanner at a candidate checkout.

    CI intentionally runs the scanner loaded from the base commit against the
    pull request working tree, so the source location and scan root may differ.
    """

    global PROJECT_ROOT, APP_ROOT
    PROJECT_ROOT = project_root.resolve()
    APP_ROOT = PROJECT_ROOT / "app"
    project_root_text = str(PROJECT_ROOT)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _python_files(root: Path) -> Iterator[Path]:
    yield from sorted(path for path in root.rglob("*.py") if path.is_file())


def _source_child_directories(root: Path) -> Set[str]:
    if not root.is_dir():
        return set()
    return {
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and path.name != "__pycache__"
        and not path.name.startswith(".")
    }


def collect_unowned_app_directories(project_root: Path) -> Set[str]:
    """Return App business/workflow directories outside the frozen target map."""

    app_root = project_root / "app"
    checks = (
        (
            app_root / "features",
            TARGET_FEATURE_DOMAINS,
        ),
        (
            app_root / "features" / "configuration",
            TARGET_CONFIGURATION_DOMAINS,
        ),
        (app_root / "orchestration", TARGET_ORCHESTRATION_DOMAINS),
        (app_root / "interfaces" / "api", frozenset({"v1"})),
        (app_root / "interfaces" / "api" / "v1", TARGET_API_V1_DOMAINS),
        (
            app_root / "interfaces" / "api" / "v1" / "admin",
            TARGET_API_ADMIN_DOMAINS,
        ),
    )
    offenders: Set[str] = set()
    for root, allowed in checks:
        for name in _source_child_directories(root) - allowed:
            offenders.add((root / name).relative_to(project_root).as_posix())
    return offenders


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_package(path: Path) -> List[str]:
    try:
        relative = path.relative_to(PROJECT_ROOT).with_suffix("")
    except ValueError:
        parts = list(path.with_suffix("").parts)
        app_index = len(parts) - 1 - parts[::-1].index("app")
        relative = Path(*parts[app_index:])
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    else:
        parts.pop()
    return parts


def _resolve_from_import(path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = _module_package(path)
    keep = max(0, len(package) - (node.level - 1))
    prefix = package[:keep]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def _imported_modules(path: Path) -> Set[str]:
    modules: Set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from_import(path, node)
            if module:
                modules.add(module)
            if node.module is None:
                modules.update(
                    f"{module}.{alias.name}" if module else alias.name
                    for alias in node.names
                    if alias.name != "*"
                )
            elif module == "app":
                modules.update(
                    f"app.{alias.name}" for alias in node.names if alias.name != "*"
                )
    return modules


def _app_layer(module: str) -> str:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "app" and parts[1] in APP_LAYERS:
        return parts[1]
    return ""


def _feature_domain(path: Path) -> str:
    relative = path.relative_to(APP_ROOT / "features")
    return relative.parts[0]


def _module_parts_after(module: str, prefix: str) -> List[str]:
    if not module.startswith(prefix):
        return []
    return module[len(prefix) :].split(".")


def _parents(tree: ast.AST) -> Dict[ast.AST, ast.AST]:
    result: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            result[child] = node
    return result


def _enclosing_callable(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> str:
    current: ast.AST = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "module"


def _enclosing_class(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> str:
    current: ast.AST = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.ClassDef):
            return current.name
    return "module"


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _annotation_names(annotation: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _route_decorators(
    node: ast.AST,
) -> Iterator[Tuple[str, str, ast.Call]]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        method = decorator.func.attr.lower()
        if method not in HTTP_METHODS:
            continue
        route = "?"
        if (
            decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and isinstance(decorator.args[0].value, str)
        ):
            route = decorator.args[0].value
        yield method.upper(), route, decorator


def _has_strict_response_model(decorator: ast.Call) -> bool:
    for keyword in decorator.keywords:
        if keyword.arg != "response_model":
            continue
        return not (
            isinstance(keyword.value, ast.Constant) and keyword.value.value is None
        )
    return False


def _response_model_names(decorator: ast.Call) -> Set[str]:
    for keyword in decorator.keywords:
        if keyword.arg == "response_model":
            return _annotation_names(keyword.value)
    return set()


def _is_non_json_handler(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if node.returns is None:
        return False
    return bool(_annotation_names(node.returns) & NON_JSON_RESPONSE_TYPES)


def _route_location(path: Path, node: ast.AST, method: str, route: str) -> str:
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return f"{_relative(path)}::{node.name}::{method} {route}"


def _scan_import_boundaries(
    violations: DefaultDict[str, Set[str]],
) -> None:
    for path in _python_files(APP_ROOT):
        relative = _relative(path)
        source_layer = path.relative_to(APP_ROOT).parts[0]
        modules = _imported_modules(path)

        for module in modules:
            target_layer = _app_layer(module)
            if module == "infrastructure" or module.startswith("infrastructure."):
                target_layer = "infrastructure"
            location = f"{relative} -> {module}"

            if source_layer == "interfaces" and target_layer in {
                "bootstrap",
                "infrastructure",
            }:
                violations["interface_forbidden_layer_imports"].add(location)
            elif source_layer == "features" and target_layer in {
                "bootstrap",
                "infrastructure",
                "interfaces",
                "orchestration",
            }:
                violations["feature_forbidden_layer_imports"].add(location)
            elif source_layer == "orchestration" and target_layer in {
                "bootstrap",
                "infrastructure",
                "interfaces",
            }:
                violations["orchestration_forbidden_layer_imports"].add(location)
            elif source_layer == "infrastructure" and target_layer in {
                "bootstrap",
                "interfaces",
            }:
                violations["infrastructure_forbidden_layer_imports"].add(location)

            if source_layer == "features" and (
                module == "fastapi" or module.startswith("fastapi.")
            ):
                violations["feature_framework_imports"].add(location)

            if source_layer == "features" and module.startswith("app.features."):
                parts = _module_parts_after(module, "app.features.")
                if len(parts) > 1 and parts[0] != _feature_domain(path):
                    violations["cross_feature_internal_imports"].add(location)

            if source_layer == "interfaces" and module.startswith("app.features."):
                parts = _module_parts_after(module, "app.features.")
                if len(parts) > 1:
                    violations["interface_feature_internal_imports"].add(location)

            if source_layer == "interfaces" and module.startswith("app.orchestration."):
                parts = _module_parts_after(module, "app.orchestration.")
                if len(parts) > 1:
                    violations["interface_orchestration_internal_imports"].add(location)

            if source_layer == "infrastructure" and module.startswith("app.features."):
                parts = _module_parts_after(module, "app.features.")
                if len(parts) > 1 and parts[-1] not in {"models", "ports"}:
                    violations["infrastructure_feature_internal_imports"].add(location)

            if source_layer == "orchestration":
                if module.startswith("app.features."):
                    parts = _module_parts_after(module, "app.features.")
                    if len(parts) > 1:
                        violations["orchestration_private_boundary_imports"].add(
                            location
                        )
                if module == "nest.godot_gateway" or module.startswith(
                    "nest.godot_gateway."
                ):
                    violations["orchestration_private_boundary_imports"].add(location)


def _scan_feature_signatures_and_tasks(
    violations: DefaultDict[str, Set[str]],
) -> None:
    for path in _python_files(APP_ROOT / "features"):
        tree = _tree(path)
        parents = _parents(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                arguments = [
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                ]
                if any(argument.arg == "db_path" for argument in arguments):
                    owner = _enclosing_class(node, parents)
                    violations["feature_public_db_path"].add(
                        f"{_relative(path)}::{owner}.{node.name}"
                    )
            elif isinstance(node, ast.Call):
                call_name = _call_name(node)
                if call_name in UNOWNED_TASK_CALLS:
                    violations["feature_unowned_task_calls"].add(
                        f"{_relative(path)}::{_enclosing_callable(node, parents)}"
                        f"::{call_name}"
                    )


def _scan_interface_construction(
    violations: DefaultDict[str, Set[str]],
) -> None:
    for path in _python_files(APP_ROOT / "interfaces"):
        tree = _tree(path)
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node)
            if not (call_name.endswith(ADAPTER_SUFFIXES) or call_name == "get_db"):
                continue
            violations["interface_adapter_construction"].add(
                f"{_relative(path)}::{_enclosing_callable(node, parents)}::{call_name}"
            )


def _scan_interface_runtime_lifecycle(
    violations: DefaultDict[str, Set[str]],
) -> None:
    forbidden_calls = UNOWNED_TASK_CALLS | frozenset(
        {"new_event_loop", "run_forever", "serve"}
    )
    for path in _python_files(APP_ROOT / "interfaces" / "api"):
        tree = _tree(path)
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node)
            if call_name not in forbidden_calls:
                continue
            violations["interface_runtime_lifecycle_calls"].add(
                f"{_relative(path)}::{_enclosing_callable(node, parents)}::{call_name}"
            )


def _annotation_has_loose_mapping(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"Any", "Dict", "Mapping", "dict", "object"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"Any", "Dict", "Mapping", "dict", "object"}
    if isinstance(node, ast.Subscript):
        return _annotation_has_loose_mapping(node.value)
    return False


def _scan_websocket_payloads(
    violations: DefaultDict[str, Set[str]],
) -> None:
    root = APP_ROOT / "interfaces" / "api" / "v1" / "realtime"
    for path in _python_files(root):
        if path.name != "models.py":
            continue
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.AnnAssign):
                continue
            if _annotation_has_loose_mapping(node.annotation):
                violations["websocket_loose_payloads"].add(
                    f"{_relative(path)}::{getattr(node.target, 'id', 'field')}"
                )


def _scan_nonstandard_error_responses(
    violations: DefaultDict[str, Set[str]],
) -> None:
    for path in _python_files(APP_ROOT / "interfaces" / "api"):
        tree = _tree(path)
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != "JSONResponse":
                continue
            keywords = {item.arg: item.value for item in node.keywords if item.arg}
            status = keywords.get("status_code")
            content = keywords.get("content")
            if not (
                isinstance(status, ast.Constant)
                and isinstance(status.value, int)
                and status.value >= 400
                and isinstance(content, ast.Dict)
            ):
                continue
            keys = {
                key.value
                for key in content.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if "detail" in keys:
                violations["nonstandard_error_responses"].add(
                    f"{_relative(path)}::{_enclosing_callable(node, parents)}"
                )


def _scan_api_route_models(
    violations: DefaultDict[str, Set[str]],
) -> None:
    for path in _python_files(APP_ROOT / "interfaces" / "api"):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = list(_route_decorators(node))
            if not decorators or _is_non_json_handler(node):
                continue

            loose_parts: Set[str] = set()
            if node.returns is None:
                loose_parts.add("return:missing")
            elif _annotation_names(node.returns) & LOOSE_OUTPUT_TYPES:
                loose_parts.add("return:loose")

            arguments = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            for argument in arguments:
                if argument.annotation is not None and (
                    _annotation_names(argument.annotation) & LOOSE_INPUT_TYPES
                ):
                    loose_parts.add(f"parameter:{argument.arg}")

            for method, route, decorator in decorators:
                location = _route_location(path, node, method, route)
                if not _has_strict_response_model(decorator):
                    violations["json_routes_missing_response_model"].add(location)
                if _response_model_names(decorator) & LOOSE_OUTPUT_TYPES:
                    loose_parts.add("response_model:loose")
                for part in loose_parts:
                    violations["json_routes_loose_annotations"].add(
                        f"{location}::{part}"
                    )


def _scan_unversioned_product_routes(
    violations: DefaultDict[str, Set[str]],
) -> None:
    from app.bootstrap import create_app

    application = create_app(db_path=":memory:")
    for route in application.routes:
        if isinstance(route, APIRoute):
            if not route.path.startswith("/api/") and not route.include_in_schema:
                continue
            if route.path.startswith("/api/v1/"):
                continue
            if route.path in PUBLIC_UNVERSIONED_HTTP_EXCEPTIONS:
                continue
            for method in sorted(route.methods or set()):
                violations["unversioned_product_routes"].add(f"{method} {route.path}")
        elif isinstance(route, WebSocketRoute):
            if route.path.startswith("/api/v1/ws/"):
                continue
            violations["unversioned_product_routes"].add(f"WS {route.path}")


def collect_app_layer_violations() -> Dict[str, FrozenSet[str]]:
    mutable: DefaultDict[str, Set[str]] = defaultdict(set)
    for rule in RULE_NAMES:
        mutable[rule]
    mutable["unowned_app_directories"].update(
        collect_unowned_app_directories(PROJECT_ROOT)
    )
    _scan_import_boundaries(mutable)
    _scan_feature_signatures_and_tasks(mutable)
    _scan_interface_construction(mutable)
    _scan_interface_runtime_lifecycle(mutable)
    _scan_api_route_models(mutable)
    _scan_websocket_payloads(mutable)
    _scan_nonstandard_error_responses(mutable)
    _scan_unversioned_product_routes(mutable)
    return {rule: frozenset(values) for rule, values in sorted(mutable.items())}


def _feature_dependency_graph(root: Path) -> Dict[str, Set[str]]:
    graph: DefaultDict[str, Set[str]] = defaultdict(set)
    for path in _python_files(root):
        source = path.relative_to(root).parts[0]
        graph[source]
        for module in _imported_modules(path):
            if not module.startswith("app.features."):
                continue
            parts = _module_parts_after(module, "app.features.")
            if parts and parts[0] != source:
                graph[source].add(parts[0])
    return dict(graph)


def _cycles(graph: Dict[str, Set[str]]) -> Set[Tuple[str, ...]]:
    found: Set[Tuple[str, ...]] = set()

    def visit(node: str, path: List[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            rotations = [
                tuple(cycle[index:-1] + cycle[:index] + [cycle[index]])
                for index in range(len(cycle) - 1)
            ]
            found.add(min(rotations))
            return
        for target in sorted(graph.get(node, set())):
            visit(target, [*path, node])

    for start in sorted(graph):
        visit(start, [])
    return found


def load_python_baseline(path: Path) -> Dict[str, FrozenSet[str]]:
    namespace = runpy.run_path(str(path))
    raw = namespace.get("LEGACY_APP_LAYER_VIOLATIONS")
    if not isinstance(raw, dict):
        raise ValueError(f"{path} does not define LEGACY_APP_LAYER_VIOLATIONS")
    return {str(rule): frozenset(entries) for rule, entries in raw.items()}


def compare_with_baseline(
    current: Dict[str, FrozenSet[str]],
    baseline: Dict[str, FrozenSet[str]],
    *,
    mode: str,
) -> List[str]:
    failures: List[str] = []
    if set(current) != set(baseline):
        failures.append(
            "rule set differs: "
            f"current_only={sorted(set(current) - set(baseline))}, "
            f"baseline_only={sorted(set(baseline) - set(current))}"
        )
        return failures
    for rule in sorted(current):
        added = sorted(current[rule] - baseline[rule])
        removed = sorted(baseline[rule] - current[rule])
        if added:
            failures.append(f"{rule}: new violations: {added}")
        if mode == "exact" and removed:
            failures.append(f"{rule}: stale baseline entries: {removed}")
    return failures


def deny_all_failures(current: Dict[str, FrozenSet[str]]) -> List[str]:
    """Reject every detected violation after the legacy baseline is deleted."""

    return [
        f"{rule}: violations are forbidden in deny-all mode: {sorted(entries)}"
        for rule, entries in sorted(current.items())
        if entries
    ]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--mode", choices=("exact", "subset", "deny-all"), default="exact"
    )
    args = parser.parse_args(argv)

    configure_project_root(args.project_root)
    current = collect_app_layer_violations()
    if args.mode == "deny-all":
        failures = deny_all_failures(current)
    else:
        if args.baseline is None:
            parser.error(f"--baseline is required in {args.mode} mode")
        baseline = load_python_baseline(args.baseline)
        failures = compare_with_baseline(current, baseline, mode=args.mode)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    total = sum(len(entries) for entries in current.values())
    print(f"App architecture {args.mode} check passed: {total} known entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
