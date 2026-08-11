"""Architecture gates for the canonical Elfie cognitive information flow."""

from __future__ import annotations

import ast
import tokenize
from pathlib import Path

import elfie as elfie_api
import elfie.body as body_api
import elfie.communication as communication_api
from elfie.body import BodyCommand, BodyPort, BodySensorEvent, CommandReceipt
from elfie.body.contracts import BodyCommand as ContractBodyCommand
from elfie.brain import BrainContext, DecisionPlan, PerceptualWorkspace
from elfie.communication import (
    CommunicationChannel,
    CommunicationEnvelope,
    DeliveryReceipt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ELFIE_ROOT = PROJECT_ROOT / "elfie"
REQUIRED_BRAIN_FILES = frozenset(
    {
        "context_types.py",
        "decision_types.py",
        "perception_types.py",
        "perceptual_workspace.py",
        "runtime_port.py",
    }
)


def test_brain_root_contains_facilities_without_a_fourth_layer_package() -> None:
    # Given
    brain_root = ELFIE_ROOT / "brain"
    entries = {path.name for path in brain_root.iterdir()}

    # When / Then
    assert REQUIRED_BRAIN_FILES <= entries
    assert not any((brain_root / "perception").glob("*.py"))
    assert not any((brain_root / "cognition").glob("*.py"))
    assert not (brain_root / "brain_types.py").exists()


def test_elfie_does_not_reverse_import_application_or_runtime_layers() -> None:
    # Given / When
    offenders: list[str] = []
    for path in ELFIE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            imported = ([module] if module is not None else []) + names
            if any(
                name.split(".", 1)[0]
                in {
                    "ai_runtime",
                    "app",
                    "godot_runtime",
                    "infrastructure",
                    "nest",
                }
                for name in imported
            ):
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
                break

    # Then
    assert offenders == []


def test_root_public_surface_is_the_stable_aggregate_facades() -> None:
    # Given / When / Then
    assert elfie_api.__all__ == ["Elfie", "ElfieFactory"]


def test_body_and_communication_ports_are_consumer_owned_protocols() -> None:
    # Given / When / Then
    assert getattr(BodyPort, "_is_protocol", False)
    assert BodyPort.__module__ == "elfie.body.port"
    assert getattr(CommunicationChannel, "_is_protocol", False)
    assert CommunicationChannel.__module__ == "elfie.communication.channel"


def test_canonical_cross_module_contracts_are_public() -> None:
    # Given
    for contract in (
        BodySensorEvent,
        CommandReceipt,
        CommunicationEnvelope,
        DeliveryReceipt,
        BrainContext,
        DecisionPlan,
    ):
        # When
        schema = contract.model_json_schema()

        # Then
        assert schema["title"] == contract.__name__
        assert schema["type"] == "object"
    assert BodyCommand is not None
    assert BodyCommand is ContractBodyCommand
    assert PerceptualWorkspace is not None


def test_old_product_cognition_entry_points_are_absent() -> None:
    # Given
    elfie_source = (ELFIE_ROOT / "elfie.py").read_text(encoding="utf-8")
    tree = ast.parse(elfie_source)
    methods = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    # When / Then
    assert methods.isdisjoint(
        {
            "perceive_and_respond",
            "perceive_body_and_respond",
            "respond_to_body_events",
        }
    )


def test_task14_legacy_body_and_communication_paths_are_absent() -> None:
    # Given: Task 14 has made the typed contracts the only product path.
    forbidden_body_exports = (
        "BodyEvent",
        "CommandResult",
        "LegacyBodyCommand",
        "LegacyBodyEvent",
        "LegacyBodyPort",
        "LegacyCommandResult",
        "LegacyCommandStatus",
    )
    forbidden_communication_exports = (
        "CommunicationMessage",
        "LegacyChannelAdapter",
        "LegacyCommunicationChannel",
        "MessageKind",
    )

    # When / Then: no public symbol or runtime adapter can restore the old path.
    assert not (ELFIE_ROOT / "nervous_system" / "legacy_perception.py").exists()
    assert all(not hasattr(body_api, name) for name in forbidden_body_exports)
    assert all(
        not hasattr(communication_api, name) for name in forbidden_communication_exports
    )
    assert "LegacyBodyPort" not in (ELFIE_ROOT / "body" / "port.py").read_text(
        encoding="utf-8"
    )
    assert "LegacyCommunicationChannel" not in (
        ELFIE_ROOT / "communication" / "channel.py"
    ).read_text(encoding="utf-8")


def test_elfie_facade_stays_within_250_pure_source_lines() -> None:
    # Given
    path = ELFIE_ROOT / "elfie.py"

    # When
    with path.open("rb") as source:
        lines = {
            token.start[0]
            for token in tokenize.tokenize(source.readline)
            if token.type
            not in {
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.COMMENT,
            }
        }

    # Then
    assert len(lines) <= 250


def test_pydantic_contracts_have_no_tracked_schema_maintenance_chain() -> None:
    # Given
    schema_root = PROJECT_ROOT / "docs" / "contracts" / "elfie" / "v1"
    scripts_root = PROJECT_ROOT / "scripts"

    # When
    schema_snapshots = tuple(schema_root.glob("*.schema.json"))
    schema_exporters = tuple(scripts_root.glob("export_*contract*schema*.py"))

    # Then
    assert schema_snapshots == ()
    assert schema_exporters == ()
