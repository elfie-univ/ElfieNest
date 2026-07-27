"""Architecture contracts for the authoritative Runtime and Observer split."""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

from app.interfaces.cli.packaged_runtime import NativeTarget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_RUNTIME_DIRECTORIES = frozenset(
    {"godot_runtime", "app/interfaces/desktop", "nest/godot_gateway"}
)
FORBIDDEN_RUNTIME_DIRECTORIES = frozenset({"desktop", "nest/godot", "nest/runtime"})
RUNTIME_HEALTH_PATH = PROJECT_ROOT / "app/orchestration/lifecycle/runtime_health.py"
HOST_CONTRACT_PATH = PROJECT_ROOT / "godot_runtime/host_contract.py"
OBSERVER_DESCRIPTOR_PATH = PROJECT_ROOT / "nest/godot_gateway/observer.py"
LIFECYCLE_CLIENT_PATH = PROJECT_ROOT / "app/interfaces/desktop/src/lifecycle_client.ts"
REQUIRED_RUNTIME_HEALTH_TYPES = frozenset(
    {"RuntimeComponent", "RuntimeHealthState", "RuntimeHealth", "OwnerLease"}
)
REQUIRED_HOST_TYPES = frozenset(
    {"RuntimeDisplayMode", "RuntimeHostKind", "RuntimeHostDescriptor"}
)
OBSERVER_DESCRIPTOR_FIELDS = frozenset(
    {"session_id", "scope", "generation", "sequence", "allowed_intents"}
)
OBSERVER_SCOPE_FIELDS = frozenset({"family_id", "room_id", "elfie_id"})
EXPECTED_RUNTIME_HEALTH_STATES = frozenset(
    {"starting", "ready", "degraded", "stopping", "stopped", "failed"}
)
EXPECTED_RUNTIME_COMPONENTS = frozenset(
    {"core", "gateway", "godot_authority", "ollama"}
)
EXPECTED_DISPLAY_MODES = frozenset({"graphical", "displayless"})
EXPECTED_HOST_KINDS = frozenset(
    {"web_authority", "electron_authority", "linux_dedicated"}
)
REQUIRED_HOST_SELECTORS = frozenset({"select_authority_host"})
EXPECTED_OBSERVER_INTENTS = frozenset({"request_resync", "focus_room", "focus_elfie"})
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


def test_authoritative_runtime_has_only_the_final_boundary_directories() -> None:
    # Given: the final Runtime architecture has explicit host, gateway and UI seams.
    missing = {
        relative_path
        for relative_path in REQUIRED_RUNTIME_DIRECTORIES
        if not (PROJECT_ROOT / relative_path).is_dir()
    }
    legacy = {
        relative_path
        for relative_path in FORBIDDEN_RUNTIME_DIRECTORIES
        if (PROJECT_ROOT / relative_path).exists()
    }

    # When / Then: no legacy Desktop or Godot protocol boundary remains.
    assert missing == set()
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


def test_runtime_health_contract_models_all_components_states_and_owner_lease() -> None:
    # Given: the Supervisor exposes one typed full-health contract.
    # When: its model declarations and closed enum values are inspected.
    # Then: all authority components, lifecycle states, generation and lease exist.
    assert RUNTIME_HEALTH_PATH.is_file()
    assert REQUIRED_RUNTIME_HEALTH_TYPES <= _class_names(RUNTIME_HEALTH_PATH)
    assert (
        _enum_values(RUNTIME_HEALTH_PATH, "RuntimeComponent")
        == EXPECTED_RUNTIME_COMPONENTS
    )
    assert (
        _enum_values(RUNTIME_HEALTH_PATH, "RuntimeHealthState")
        == EXPECTED_RUNTIME_HEALTH_STATES
    )
    assert {"generation", "owner_lease"} <= set(
        _class_field_annotations(RUNTIME_HEALTH_PATH, "RuntimeHealth")
    )
    assert {"owner_id", "generation"} <= set(
        _class_field_annotations(RUNTIME_HEALTH_PATH, "OwnerLease")
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


def test_observer_descriptor_has_only_scoped_read_capability_and_high_level_intents() -> (
    None
):
    # Given: an Observer descriptor is a closed typed subscription identity.
    # When: every descriptor and nested scope field is allowlisted structurally.
    # Then: aliases cannot smuggle in credentials, capabilities or world transforms.
    assert OBSERVER_DESCRIPTOR_PATH.is_file()
    annotations = _class_field_annotations(
        OBSERVER_DESCRIPTOR_PATH, "ObserverDescriptor"
    )
    scope_annotations = _class_field_annotations(
        OBSERVER_DESCRIPTOR_PATH, "ObserverScope"
    )
    assert set(annotations) == OBSERVER_DESCRIPTOR_FIELDS
    assert set(scope_annotations) == OBSERVER_SCOPE_FIELDS
    assert annotations["session_id"] == "str"
    assert annotations["scope"] == "ObserverScope"
    assert annotations["generation"] == "int"
    assert annotations["sequence"] == "int"
    assert "ObserverIntent" in annotations["allowed_intents"]
    assert set(scope_annotations.values()) <= {"str", "str | None"}
    assert {"str", "Enum"} <= _class_bases(OBSERVER_DESCRIPTOR_PATH, "ObserverIntent")
    assert _enum_values(OBSERVER_DESCRIPTOR_PATH, "ObserverIntent") == (
        EXPECTED_OBSERVER_INTENTS
    )


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
