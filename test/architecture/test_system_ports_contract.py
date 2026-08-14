"""Permanent ratchets for the final system Port/Adapter boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STRICT_BOUNDARY_FILES = (
    "infrastructure/models/model_execution_ports.py",
    "infrastructure/models/storage_ports.py",
    "infrastructure/models/report_records.py",
    "infrastructure/models/model_execution_contracts.py",
    "infrastructure/models/inference/model_guard.py",
    "infrastructure/godot/nest_session/ports.py",
    "infrastructure/godot/body_transport.py",
    "app/orchestration/message_delivery/owner_channel.py",
    "app/orchestration/nest_session/ports.py",
    "elfie/brain/reasoning/food_port.py",
    "elfie/brain/reasoning/tool_port.py",
    "elfie/body/port.py",
    "elfie/body/capabilities.py",
    "elfie/body/types.py",
    "elfie/profile/port.py",
    "app/orchestration/nest_session/runtime_events.py",
    "infrastructure/models/inference/token_usage.py",
    "infrastructure/models/validation/agent_validation.py",
    "infrastructure/models/validation/provider_model_benchmark.py",
    "infrastructure/models/model_execution_observations.py",
    "infrastructure/tools/capability_configuration.py",
    "infrastructure/tools/port_adapter.py",
    "infrastructure/persistence/report_storage.py",
)


def _tree(relative_path: str) -> ast.Module:
    return ast.parse(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8"),
        filename=relative_path,
    )


def test_system_boundary_modules_have_no_dynamic_any_or_object_contracts() -> None:
    offenders: list[str] = []
    for relative_path in STRICT_BOUNDARY_FILES:
        tree = _tree(relative_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in {"Any", "object"}:
                offenders.append(f"{relative_path}:{node.id}")
    assert offenders == []


def test_all_protocol_method_annotations_are_strict() -> None:
    offenders: list[str] = []
    for root_name in ("app", "elfie", "nest", "infrastructure"):
        for path in (PROJECT_ROOT / root_name).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for class_node in ast.walk(tree):
                if not isinstance(class_node, ast.ClassDef):
                    continue
                is_protocol = any(
                    (isinstance(base, ast.Name) and base.id == "Protocol")
                    or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
                    for base in class_node.bases
                )
                if not is_protocol:
                    continue
                for method in class_node.body:
                    if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    annotations = [method.returns]
                    annotations.extend(
                        argument.annotation
                        for argument in (
                            *method.args.posonlyargs,
                            *method.args.args,
                            *method.args.kwonlyargs,
                        )
                        if argument.annotation is not None
                    )
                    for annotation in annotations:
                        if annotation is None:
                            continue
                        names = {
                            node.id
                            for node in ast.walk(annotation)
                            if isinstance(node, ast.Name)
                        }
                        if names & {"Any", "object"}:
                            offenders.append(
                                f"{path.relative_to(PROJECT_ROOT)}:{method.lineno}"
                            )
    assert offenders == []


def test_infrastructure_capabilities_do_not_import_concrete_peer_adapters() -> None:
    offenders: list[str] = []
    concrete_suffixes = (
        "Adapter",
        "Repository",
        "Store",
        "Plugin",
        "Connector",
    )
    root = PROJECT_ROOT / "infrastructure"
    for path in root.rglob("*.py"):
        source_package = path.relative_to(root).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("infrastructure."):
                continue
            target_package = node.module.split(".")[1]
            if target_package == source_package:
                continue
            for imported in node.names:
                if imported.name.endswith(concrete_suffixes):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT).as_posix()} -> "
                        f"{node.module}.{imported.name}"
                    )
    assert offenders == []


def test_communication_platform_and_authenticated_ingress_have_one_direction() -> None:
    domain_root = PROJECT_ROOT / "elfie" / "communication"
    domain_offenders: list[str] = []
    for path in domain_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            if any(
                module.startswith(("app", "infrastructure", "nest"))
                for module in modules
            ):
                domain_offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert domain_offenders == []

    for relative_path in (
        "infrastructure/communication/channels/wechat.py",
        "infrastructure/communication/channels/telegram.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "elfie.communication.contracts" in source
        assert "from app." not in source
        assert "from nest." not in source

    conversation_route = (
        PROJECT_ROOT / "app/interfaces/api/v1/me/conversations/routes.py"
    ).read_text(encoding="utf-8")
    chat_route = (
        PROJECT_ROOT / "app/interfaces/api/v1/realtime/chat/routes.py"
    ).read_text(encoding="utf-8")
    for source in (conversation_route, chat_route):
        assert "require_user" in source or "authenticate_session" in source
        assert "MessageDeliveryFacade" in source
        assert "infrastructure." not in source
    assert 'prefix="/api/v1/me/conversations"' in conversation_route
    assert '"/ws/chat"' in chat_route


def test_bootstrap_is_the_only_production_communication_adapter_composition_root() -> (
    None
):
    wiring = (PROJECT_ROOT / "app/bootstrap/app_wiring/communication.py").read_text(
        encoding="utf-8"
    )
    assert "SQLiteConversationHistoryAdapter" in wiring
    assert "ElfieMessageDeliveryAdapter" in wiring
    assert "SameOriginMessagePublisher" in wiring
    for relative_path in (
        "app/interfaces/api/v1/me/conversations/routes.py",
        "app/interfaces/api/v1/realtime/chat/routes.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "SQLiteConversationHistoryAdapter" not in source
        assert "SameOriginMessagePublisher" not in source
