"""Architecture contracts for the authoritative Runtime and Observer split."""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path

from app.interfaces.cli.packaged_runtime import NativeTarget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_RUNTIME_DIRECTORIES = frozenset({"desktop", "nest/godot", "nest/runtime"})
RUNTIME_SNAPSHOT_PATH = PROJECT_ROOT / "app/orchestration/lifecycle/runtime_snapshot.py"
GODOT_MAIN_PATH = PROJECT_ROOT / "godot_project/main.gd"
GODOT_NEST_PATH = PROJECT_ROOT / "godot_project/rooms/nest.gd"
GODOT_OBSERVER_BRIDGE_PATH = (
    PROJECT_ROOT / "godot_project/runtime/observer/observer_bridge.gd"
)
LIFECYCLE_CLIENT_PATH = PROJECT_ROOT / "app/interfaces/desktop/src/lifecycle_client.ts"
REQUIRED_RUNTIME_SNAPSHOT_TYPES = frozenset(
    {
        "RuntimeComponent",
        "ComponentState",
        "BackendTier",
        "RuntimePhase",
        "RuntimeTarget",
        "RuntimeSnapshotV1",
        "RuntimeProjectionV1",
        "OwnerLease",
    }
)
REQUIRED_HOST_TYPES = frozenset(
    {"RuntimeDisplayMode", "RuntimeHostKind", "RuntimeHostDescriptor"}
)
OBSERVER_API_MODELS_PATH = PROJECT_ROOT / "app/interfaces/api/v1/observer/models.py"
NEST_SEMANTIC_MODEL_PATH = PROJECT_ROOT / "app/orchestration/nest_session/models.py"
EXPECTED_BACKEND_TIERS = frozenset({"offline", "core_ready", "world_ready"})
EXPECTED_RUNTIME_COMPONENTS = frozenset(
    {"core", "gateway", "godot_authority", "ollama"}
)
EXPECTED_DISPLAY_MODES = frozenset({"graphical", "displayless"})
EXPECTED_HOST_KINDS = frozenset(
    {"web_authority", "electron_authority", "linux_dedicated"}
)
REQUIRED_HOST_SELECTORS = frozenset({"select_authority_host"})
EXPECTED_GODOT_OBSERVER_ACTIONS = frozenset(
    {
        "overview",
        "select",
        "reset",
        "set_local_presentation_paused",
    }
)
EXPECTED_GODOT_OBSERVER_CATALOG_FIELDS = frozenset(
    {"revision", "views", "active_id", "presentation_paused"}
)
EXPECTED_GODOT_OBSERVER_VIEW_FIELDS = frozenset({"id", "label"})
EXPECTED_GODOT_OBSERVER_TRANSPORT_FIELDS = frozenset({"channel", "version", "kind"})
EXPECTED_OBSERVER_PRESENTATION_FIELDS = frozenset(
    {
        "room_id",
        "zone_id",
        "posture",
        "active",
        "active_command_id",
        "species_id",
        "appearance",
        "home_anchor_id",
    }
)


HOST_CONTRACT_PATH = PROJECT_ROOT / "infrastructure/godot/lifecycle/host_contract.py"
FORBIDDEN_GODOT_OBSERVER_BOUNDARY_FIELDS = frozenset(
    {
        "x",
        "y",
        "z",
        "position",
        "positions",
        "transform",
        "transforms",
        "fov",
        "coordinates",
        "frame",
        "frames",
        "credential",
        "credentials",
        "token",
        "nonce",
        "authority",
    }
)
FORBIDDEN_GODOT_OBSERVER_ACTIONS = frozenset({"previous", "next"})
EXPECTED_GODOT_OBSERVER_ACTION_KEY_RULES = {
    "overview": frozenset(),
    "select": frozenset({"view_id"}),
    "reset": frozenset(),
    "set_local_presentation_paused": frozenset({"paused"}),
}
EXPECTED_GODOT_OBSERVER_VIEW_IDS = frozenset(
    {"overview", "section-%02d", "activity-%02d", "dorm-%02d", "portal"}
)
EXPECTED_NATIVE_TARGETS = frozenset(
    {
        "darwin-arm64",
        "darwin-x64",
        "win32-x64",
        "linux-x64",
    }
)
FORBIDDEN_DESKTOP_AUTHORITY_TOKENS = frozenset(
    {
        "RuntimeSupervisor",
        "SupervisorConfig",
        "createHiddenGodotRuntime",
        "appendRuntimeCredentials",
        "camera_token",
        "godotNonce",
        "godotCameraToken",
    }
)
DESKTOP_SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx"})
DESKTOP_CONFIGURATION_NAMES = frozenset(
    {
        "package.json",
        "tsconfig.json",
        "electron-builder.yml",
        "electron-builder.json",
    }
)


def _class_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _class_field_annotations(path: Path, class_name: str) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                statement.target.id: ast.unparse(statement.annotation)
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            }
    return {}


def _enum_values(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        return {
            statement.value.value
            for statement in node.body
            if isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        }
    return set()


def _class_bases(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        ast.unparse(base)
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
        for base in node.bases
    }


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def _gdscript_function_body(path: Path, function_name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    signature_prefix = f"func {function_name}("
    start_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith(signature_prefix)
        ),
        None,
    )
    if start_index is None:
        raise AssertionError(f"GDScript function not found: {function_name}")
    end_index = next(
        (
            index
            for index in range(start_index + 1, len(lines))
            if lines[index].startswith("func ")
        ),
        len(lines),
    )
    return "\n".join(lines[start_index:end_index])


def _gdscript_braced_block(source: str, marker: str) -> str:
    marker_index = source.find(marker)
    if marker_index < 0:
        raise AssertionError(f"GDScript marker not found: {marker}")
    open_index = source.find("{", marker_index)
    if open_index < 0:
        raise AssertionError(f"GDScript braced block not found after: {marker}")
    depth = 0
    for index in range(open_index, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[open_index : index + 1]
    raise AssertionError(f"GDScript braced block is unterminated after: {marker}")


def _gdscript_literal_keys(source: str) -> set[str]:
    return set(re.findall(r'^\s*"([^"]+)":', source, flags=re.MULTILINE))


def _gdscript_string_literals(source: str) -> set[str]:
    return set(re.findall(r'"([^"]*)"', source))


def _gdscript_match_cases(source: str) -> set[str]:
    return set(re.findall(r'^\s*"([^"]+)":\s*$', source, flags=re.MULTILINE))


def _assert_tokens_in_order(source: str, tokens: tuple[str, ...]) -> None:
    position = -1
    for token in tokens:
        next_position = source.find(token, position + 1)
        assert next_position > position, token
        position = next_position


def _gdscript_observer_action_key_rules(source: str) -> dict[str, frozenset[str]]:
    matches = re.findall(
        r'"([^"]+)":\s*\n\s*return _has_exact_keys\('
        r"message,\s*\[([^\]]*)\]\s*\)",
        source,
    )
    base_keys = {"channel", "version", "kind", "action"}
    return {
        action: frozenset(re.findall(r'"([^"]+)"', allowed_keys)) - base_keys
        for action, allowed_keys in matches
    }


def _desktop_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.suffix in DESKTOP_SOURCE_SUFFIXES
            or path.name in DESKTOP_CONFIGURATION_NAMES
        )
    )


def _export_presets() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    source = (PROJECT_ROOT / "godot_project/export_presets.cfg").read_text(
        encoding="utf-8"
    )
    parser.read_string(source.replace('"', ""))
    return parser


def test_removed_runtime_boundary_aliases_are_not_restored() -> None:
    # Current migration paths may move to Infrastructure; removed aliases stay absent.
    legacy = {
        relative_path
        for relative_path in FORBIDDEN_RUNTIME_DIRECTORIES
        if (PROJECT_ROOT / relative_path).exists()
    }

    # When / Then: no legacy Desktop or Godot protocol boundary remains.
    assert legacy == set()


def test_desktop_interface_contains_no_supervisor_or_authority_protocol() -> None:
    # Given: Desktop is only UI/platform integration plus a public lifecycle client.
    desktop_root = PROJECT_ROOT / "app/interfaces/desktop"
    sources = _desktop_files(desktop_root) if desktop_root.is_dir() else ()

    # When: source, JSX and package/build entrypoints are checked for authority.
    offenders = {
        source.relative_to(PROJECT_ROOT).as_posix(): sorted(
            token
            for token in FORBIDDEN_DESKTOP_AUTHORITY_TOKENS
            if token in source.read_text(encoding="utf-8")
        )
        for source in sources
        if any(
            token in source.read_text(encoding="utf-8")
            for token in FORBIDDEN_DESKTOP_AUTHORITY_TOKENS
        )
    }

    # Then: Supervisor and authority credentials live outside the Desktop UI.
    assert desktop_root.is_dir()
    assert LIFECYCLE_CLIENT_PATH.is_file()
    assert not (desktop_root / "src/supervisor").exists()
    assert offenders == {}


def test_runtime_snapshot_contract_models_stable_tiers_and_generation() -> None:
    # Given: the lifecycle exposes one versioned authoritative snapshot.
    # When: its model declarations and closed enum values are inspected.
    # Then: all authority components, lifecycle states, generation and lease exist.
    assert RUNTIME_SNAPSHOT_PATH.is_file()
    assert REQUIRED_RUNTIME_SNAPSHOT_TYPES <= _class_names(RUNTIME_SNAPSHOT_PATH)
    assert (
        _enum_values(RUNTIME_SNAPSHOT_PATH, "RuntimeComponent")
        == EXPECTED_RUNTIME_COMPONENTS
    )
    assert _enum_values(RUNTIME_SNAPSHOT_PATH, "BackendTier") == EXPECTED_BACKEND_TIERS
    assert {
        "schema_version",
        "instance_id",
        "generation",
        "revision",
        "tier",
        "phase",
        "desired_target",
        "components",
    } <= set(_class_field_annotations(RUNTIME_SNAPSHOT_PATH, "RuntimeSnapshotV1"))
    assert {"owner_id", "generation"} <= set(
        _class_field_annotations(RUNTIME_SNAPSHOT_PATH, "OwnerLease")
    )


def test_typed_host_contract_separates_graphical_and_displayless_authority_hosts() -> (
    None
):
    # Given / When: the explicit host model is inspected without importing it early.
    assert HOST_CONTRACT_PATH.is_file()
    assert REQUIRED_HOST_TYPES <= _class_names(HOST_CONTRACT_PATH)
    assert {"str", "Enum"} <= _class_bases(HOST_CONTRACT_PATH, "RuntimeHostKind")
    assert {"str", "Enum"} <= _class_bases(HOST_CONTRACT_PATH, "RuntimeDisplayMode")
    assert (
        _enum_values(HOST_CONTRACT_PATH, "RuntimeDisplayMode") == EXPECTED_DISPLAY_MODES
    )
    assert _enum_values(HOST_CONTRACT_PATH, "RuntimeHostKind") == EXPECTED_HOST_KINDS
    annotations = _class_field_annotations(HOST_CONTRACT_PATH, "RuntimeHostDescriptor")

    # Then: graphical authorities and the Linux displayless authority are selectable.
    assert {"kind", "display_mode"} <= set(annotations)
    assert annotations["kind"] == "RuntimeHostKind"
    assert annotations["display_mode"] == "RuntimeDisplayMode"
    assert REQUIRED_HOST_SELECTORS <= _function_names(HOST_CONTRACT_PATH)


def test_native_targets_are_the_closed_four_target_input_enum() -> None:
    # Given: release and runtime packaging share the typed native target input.
    targets = frozenset(target.value for target in NativeTarget)

    # When / Then: split macOS targets are accepted; universal and fifth are not.
    assert targets == EXPECTED_NATIVE_TARGETS
    assert NativeTarget("darwin-arm64") is NativeTarget.DARWIN_ARM64
    assert NativeTarget("darwin-x64") is NativeTarget.DARWIN_X64
    for unsupported_target in ("darwin-universal", "freebsd-x64"):
        try:
            NativeTarget(unsupported_target)
        except ValueError:
            continue
        raise AssertionError(
            f"unsupported native target was accepted: {unsupported_target}"
        )


def test_observer_api_models_have_scoped_access_and_high_level_intents() -> None:
    # Given: the versioned Observer API owns capability/session wire models.
    # Then: requests are closed to the observer role and bounded interactions.
    assert OBSERVER_API_MODELS_PATH.is_file()
    session_fields = _class_field_annotations(
        OBSERVER_API_MODELS_PATH, "OpenObserverSessionRequest"
    )
    subscription_fields = _class_field_annotations(
        OBSERVER_API_MODELS_PATH, "ObserverSubscriptionResponse"
    )
    intent_fields = _class_field_annotations(
        OBSERVER_API_MODELS_PATH, "ObserverIntentRequest"
    )
    assert set(session_fields) == {"protocol", "role", "subscription"}
    assert session_fields["protocol"] == "Literal[3]"
    assert session_fields["role"] == "Literal['observer']"
    assert set(subscription_fields) == {"kind", "room_id", "elfie_id"}
    assert set(intent_fields) == {"kind", "actor_id", "interaction"}
    assert intent_fields["kind"] == "Literal['request_interaction']"


def test_godot_observer_catalog_is_semantic_versioned_and_not_authority() -> None:
    # Given: Product web observes Godot through a semantic camera catalog only.
    catalog_body = _gdscript_function_body(GODOT_NEST_PATH, "observer_camera_catalog")
    register_body = _gdscript_function_body(
        GODOT_NEST_PATH, "_register_observation_view"
    )
    rebuild_body = _gdscript_function_body(GODOT_NEST_PATH, "_build_observation_views")
    section_views_body = _gdscript_function_body(
        GODOT_NEST_PATH, "_build_section_observation_views"
    )
    select_view_body = _gdscript_function_body(
        GODOT_NEST_PATH, "select_observation_view"
    )
    select_by_id_body = _gdscript_function_body(
        GODOT_NEST_PATH, "select_observer_camera_by_id"
    )
    reset_observer_body = _gdscript_function_body(
        GODOT_NEST_PATH, "reset_observer_camera"
    )
    public_catalog_api_bodies = "\n".join(
        _gdscript_function_body(GODOT_NEST_PATH, function_name)
        for function_name in (
            "observer_camera_catalog",
            "observer_presentation_paused",
            "select_observer_camera_by_id",
            "select_observer_overview",
            "reset_observer_camera",
            "set_observer_presentation_paused",
        )
    )
    publish_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "publish_catalog"
    )
    bridge_source = GODOT_OBSERVER_BRIDGE_PATH.read_text(encoding="utf-8")

    # When / Then: the internal catalog is exactly semantic id/label metadata.
    assert (
        _gdscript_literal_keys(_gdscript_braced_block(catalog_body, "views.append"))
        == EXPECTED_GODOT_OBSERVER_VIEW_FIELDS
    )
    assert (
        _gdscript_literal_keys(_gdscript_braced_block(catalog_body, "return"))
        == EXPECTED_GODOT_OBSERVER_CATALOG_FIELDS
    )
    assert FORBIDDEN_GODOT_OBSERVER_BOUNDARY_FIELDS.isdisjoint(
        _gdscript_string_literals(public_catalog_api_bodies)
    )

    # And: registrations preserve stable semantic ids, while unknown selection
    # returns false before any active-camera mutation or fallback selection.
    registration_sources = rebuild_body + "\n" + section_views_body
    assert EXPECTED_GODOT_OBSERVER_VIEW_IDS <= _gdscript_string_literals(
        registration_sources
    )
    assert _gdscript_literal_keys(
        _gdscript_braced_block(register_body, "_camera_views.append")
    ) == frozenset({"id", "label", "camera", "target", "transform", "size", "fov"})
    _assert_tokens_in_order(
        rebuild_body,
        (
            "var previous_id := _active_camera_id",
            "_active_camera_index = _observation_view_index_by_id(previous_id)",
            '_active_camera_index = _observation_view_index_by_id("overview")',
            "_active_camera_index = 0",
            "select_observation_view(_active_camera_index)",
        ),
    )
    _assert_tokens_in_order(
        select_by_id_body,
        (
            "if _observer_presentation_paused:",
            "return false",
            "var index := _observation_view_index_by_id(view_id)",
            "if index < 0:",
            "return false",
            "select_observation_view(index)",
            "return true",
        ),
    )
    assert "_active_camera_index =" not in select_by_id_body
    assert "_active_camera_id =" not in select_by_id_body
    assert "_observer_presentation_paused" not in select_view_body
    assert '_active_camera_id = String(view["id"])' in select_view_body
    assert "_observer_presentation_paused" in reset_observer_body

    # And: the Web transport adds only channel/version/kind around the catalog.
    assert 'OBSERVER_CHANNEL := "elfienest.observer"' in bridge_source
    assert "OBSERVER_PROTOCOL_VERSION := 1" in bridge_source
    assert "nest.observer_camera_catalog()" in publish_body
    assert (
        _gdscript_literal_keys(_gdscript_braced_block(publish_body, ".merged"))
        == EXPECTED_GODOT_OBSERVER_TRANSPORT_FIELDS
    )
    assert '"kind": "camera_catalog"' in publish_body
    assert "JavaScriptBridge.eval" in publish_body
    assert "window.parent.postMessage" in publish_body


def test_product_observer_accepts_only_semantic_actor_snapshots() -> None:
    # Given: the product Observer needs render inputs but not authority frames.
    source = GODOT_MAIN_PATH.read_text(encoding="utf-8")
    bridge_source = GODOT_OBSERVER_BRIDGE_PATH.read_text(encoding="utf-8")
    ready_body = _gdscript_function_body(GODOT_MAIN_PATH, "_ready")
    setup_body = _gdscript_function_body(GODOT_OBSERVER_BRIDGE_PATH, "setup_web_bridge")
    poll_body = _gdscript_function_body(GODOT_OBSERVER_BRIDGE_PATH, "process_frame")
    accepts_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "_accepts_camera_command"
    )
    exact_keys_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "_has_exact_keys"
    )
    parser_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "_parse_camera_command"
    )
    presentation_mode_body = _gdscript_function_body(
        GODOT_MAIN_PATH, "_enter_product_observer_presentation_mode"
    )
    local_pause_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "_set_local_presentation_paused"
    )
    observer_fields = _class_field_annotations(
        NEST_SEMANTIC_MODEL_PATH, "ObserverSemanticEntity"
    )
    semantic_parser_body = _gdscript_function_body(
        GODOT_OBSERVER_BRIDGE_PATH, "_parse_semantic_snapshot"
    )

    # Then: semantic actor inputs are explicit and the bridge remains view-only.
    assert EXPECTED_OBSERVER_PRESENTATION_FIELDS <= set(observer_fields)
    assert "data.kind === 'semantic_snapshot'" in bridge_source
    assert "_parse_semantic_snapshot" in bridge_source
    assert "_runtime_client = null" not in source
    assert "position" not in semantic_parser_body

    # And: the bridge exists only in product observer mode and its injected
    # listener checks origin, then parent source, before queueing parsed commands.
    _assert_tokens_in_order(
        ready_body,
        (
            "_product_observer_mode = (",
            "_query_parameter(OBSERVER_MODE_PARAMETER) == OBSERVER_MODE_VALUE",
            "if _product_observer_mode:",
            "_enter_product_observer_presentation_mode()",
            "nest.show_observation_hud = false",
            "_setup_product_observer_bridge()",
        ),
    )
    _assert_tokens_in_order(
        setup_body,
        (
            'not OS.has_feature("web")',
            "JavaScriptBridge.eval",
            "window.__elfieNestObserverQueue = window.__elfieNestObserverQueue || []",
            "event.origin !== window.location.origin",
            "event.source !== window.parent",
            "data.channel === 'elfienest.observer'",
            "data.version === 1",
            "data.kind === 'camera_command'",
            "__elfieNestObserverQueue.push",
        ),
    )
    _assert_tokens_in_order(
        poll_body,
        (
            "JSON.parse_string(String(raw_message))",
            "_parse_camera_command",
            "_handle_camera_command",
        ),
    )

    # And: command parsing is a closed semantic vocabulary with exact
    # action-specific key allowlists; free-form, previous, next, nested payloads,
    # extra fields and coordinate-bearing commands are rejected outside those cases.
    assert _gdscript_match_cases(parser_body) == EXPECTED_GODOT_OBSERVER_ACTIONS
    assert FORBIDDEN_GODOT_OBSERVER_ACTIONS.isdisjoint(
        _gdscript_string_literals(parser_body)
    )
    assert (
        _gdscript_observer_action_key_rules(accepts_body)
        == EXPECTED_GODOT_OBSERVER_ACTION_KEY_RULES
    )
    assert "expected_keys" in exact_keys_body
    assert "value.keys().size() != expected_keys.size()" in exact_keys_body
    assert "for key: Variant in value.keys():" in exact_keys_body
    assert "if typeof(key) != TYPE_STRING:" in exact_keys_body
    assert "if key not in expected_keys:" in exact_keys_body
    assert 'typeof(message.get("channel")) != TYPE_STRING' in accepts_body
    assert 'var version: Variant = message.get("version")' in accepts_body
    assert "if typeof(version) == TYPE_INT:" in accepts_body
    assert "elif typeof(version) == TYPE_FLOAT:" in accepts_body
    assert "if version != float(OBSERVER_PROTOCOL_VERSION):" in accepts_body
    assert 'typeof(message.get("kind")) != TYPE_STRING' in accepts_body
    assert 'typeof(message.get("action")) != TYPE_STRING' in accepts_body
    assert "String(message.get" not in accepts_body
    assert "int(message.get" not in accepts_body
    assert "return false" in accepts_body
    assert "not _enabled or not _accepts_camera_command(message)" in (parser_body)
    _assert_tokens_in_order(parser_body, ("_:", "return {}"))
    assert FORBIDDEN_GODOT_OBSERVER_BOUNDARY_FIELDS.isdisjoint(
        _gdscript_string_literals(parser_body)
    )

    # And: observer pause is local presentation only. Product observer keeps
    # polling parent bridge commands while the local SceneTree is paused, and the
    # pause path does not own or invoke authority transport state.
    assert "process_mode = Node.PROCESS_MODE_ALWAYS" in presentation_mode_body
    _assert_tokens_in_order(
        local_pause_body,
        (
            "nest.set_observer_presentation_paused(paused)",
            "if is_inside_tree():",
            "get_tree().paused = paused",
        ),
    )
    for runtime_token in (
        "_runtime_client",
        "_world_controller",
        "_actor_controller",
        "_semantic_events",
        "_start_authority_runtime",
        "_send_runtime_event",
    ):
        assert runtime_token not in local_pause_body


def test_godot_export_configuration_declares_web_and_linux_dedicated_outputs() -> None:
    # Given: authority Runtime exports are source-controlled Godot configuration.
    export_presets = _export_presets()
    script_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "scripts").glob("*.py")
    )

    # When / Then: Web and Linux Dedicated outputs are independently declared.
    web = export_presets["preset.0"]
    dedicated = [
        export_presets[section]
        for section in export_presets.sections()
        if section.startswith("preset.")
        and not section.endswith(".options")
        and export_presets[section].get("platform", "").lower().startswith("linux")
    ]
    assert web["platform"].lower() == "web"
    assert web.getboolean("runnable")
    assert not web.getboolean("dedicated_server")
    assert "build/components/godot-web/" in web["export_path"]
    assert len(dedicated) == 1
    assert dedicated[0].getboolean("runnable")
    assert dedicated[0].getboolean("dedicated_server")
    assert "build/components/godot-linux-dedicated/" in dedicated[0]["export_path"]
    assert "build/components/godot-linux-dedicated" in script_sources
