"""Architecture gates for the unified brain observation surface (ADR-0037).

The surface is `elfie/brain/observation.py` plus one named payload module per
boundary group. These gates keep the modules domain-pure, keep the payloads
strongly typed and keep the on-disk Schema ban that governs every Pydantic
contract.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRAIN_ROOT = PROJECT_ROOT / "elfie" / "brain"

OBSERVATION_SURFACE_MODULES = (
    BRAIN_ROOT / "observation.py",
    BRAIN_ROOT / "reasoning" / "observation_payloads.py",
    BRAIN_ROOT / "reasoning" / "agent_loop_observations.py",
    BRAIN_ROOT / "reasoning" / "run_controller_observations.py",
    BRAIN_ROOT / "reasoning" / "coordinator_observations.py",
    BRAIN_ROOT / "activity" / "observation_payloads.py",
    BRAIN_ROOT / "memory" / "observation_payloads.py",
)

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"ai_runtime", "app", "devtools", "godot_runtime", "infrastructure", "nest"}
)
UNTYPED_ANNOTATION_PATTERN = re.compile(r"\b(Any|dict|Dict)\b")


def _offending_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        module = node.module if isinstance(node, ast.ImportFrom) else None
        names = (
            [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
        )
        imported = ([module] if module is not None else []) + names
        for name in imported:
            if name.split(".", 1)[0] in FORBIDDEN_IMPORT_ROOTS:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno} "
                    f"imports {name}"
                )
    return offenders


def _annotation_offence(annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Constant):
        if isinstance(annotation.value, str) and UNTYPED_ANNOTATION_PATTERN.search(
            annotation.value
        ):
            return annotation.value
        return None
    if isinstance(annotation, ast.Name):
        if annotation.id in {"Any", "dict", "Dict"}:
            return annotation.id
        return None
    if isinstance(annotation, ast.Attribute):
        if annotation.attr in {"Any", "dict", "Dict"}:
            return annotation.attr
        return None
    if isinstance(annotation, ast.Subscript):
        return _annotation_offence(annotation.value)
    return None


def _annotation_nodes(tree: ast.AST) -> list[ast.expr]:
    annotations: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                annotations.append(node.returns)
    return annotations


def test_observation_surface_modules_import_no_application_infrastructure_or_devtools() -> (
    None
):
    for path in OBSERVATION_SURFACE_MODULES:
        assert path.is_file(), f"missing observation surface module: {path}"

    offenders: list[str] = []
    for path in OBSERVATION_SURFACE_MODULES:
        offenders.extend(_offending_imports(path))

    assert offenders == []


def test_observation_surface_modules_have_no_any_or_raw_dict_annotations() -> None:
    offenders: list[str] = []
    for path in OBSERVATION_SURFACE_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for annotation in _annotation_nodes(tree):
            offence = _annotation_offence(annotation)
            if offence is not None:
                offenders.append(f"{relative}: annotation uses {offence}")

    assert offenders == []


def test_observation_contracts_have_no_tracked_schema_maintenance_chain() -> None:
    # Given: the same on-disk schema ban as the canonical Elfie contracts —
    # code models are the single contract source, so no exported schema files
    # or exporter scripts may exist for the observation surface.
    schema_root = PROJECT_ROOT / "docs" / "contracts"
    scripts_root = PROJECT_ROOT / "scripts"

    # When
    schema_snapshots = (
        [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in schema_root.rglob("*.schema.json")
            if "observation" in path.name.lower()
        ]
        if schema_root.is_dir()
        else []
    )
    schema_exporters = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in scripts_root.rglob("export_*observation*schema*.py")
    ]

    # Then
    assert schema_snapshots == []
    assert schema_exporters == []


def test_observation_surface_keeps_the_typed_port_and_payload_registration() -> None:
    # Given / When / Then: the Port, envelope and null sink stay Brain-owned.
    from elfie.brain.observation import (
        BrainObservation,
        BrainObservationSink,
        NoOpSink,
    )

    assert getattr(BrainObservationSink, "_is_protocol", False)
    assert BrainObservationSink.__module__ == "elfie.brain.observation"
    assert BrainObservation.__module__ == "elfie.brain.observation"

    sink = NoOpSink()
    assert sink.snapshot() == ()


def test_each_boundary_group_owns_named_frozen_payload_models() -> None:
    payload_modules = OBSERVATION_SURFACE_MODULES[1:]

    for path in payload_modules:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        payload_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(
                isinstance(base, ast.Name) and base.id == "FrozenContractModel"
                for base in node.bases
            )
        ]
        assert payload_classes, (
            f"{path.relative_to(PROJECT_ROOT).as_posix()} owns no named payload model"
        )
