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
from elfie.brain import (
    BrainContext,
    DecisionPlan,
    EventWorkspace,
    ToolPort,
    ToolRequest,
    ToolResult,
)
from elfie.communication import (
    CommunicationChannel,
    CommunicationEnvelope,
    DeliveryReceipt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ELFIE_ROOT = PROJECT_ROOT / "elfie"
REQUIRED_BRAIN_SYSTEMS = frozenset(
    {
        "workspace",
        "orientation",
        "selfhood",
        "emotion",
        "energy",
        "motivation",
        "memory",
        "reasoning",
        "activity",
        "consolidation",
    }
)
FORBIDDEN_FLAT_BRAIN_MODULES = frozenset(
    {
        "activity.py",
        "context_builder.py",
        "context_source.py",
        "context_types.py",
        "cortical_worker.py",
        "limbic_appraiser.py",
        "motivation.py",
        "offline_cognition.py",
        "orientation.py",
        "perception_types.py",
        "perceptual_workspace.py",
        "selfhood.py",
    }
)


def test_brain_has_ten_owned_system_packages_without_flat_legacy_duplicates() -> None:
    # Given
    brain_root = ELFIE_ROOT / "brain"
    entries = {path.name for path in brain_root.iterdir()}

    # When / Then
    assert REQUIRED_BRAIN_SYSTEMS <= entries
    assert all(
        (brain_root / name / "__init__.py").is_file() for name in REQUIRED_BRAIN_SYSTEMS
    )
    assert FORBIDDEN_FLAT_BRAIN_MODULES.isdisjoint(entries)


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


def test_app_inbound_callers_use_curated_elfie_and_nest_surfaces() -> None:
    """App callers do not reach through domain internals for production entry points."""
    offenders: list[str] = []
    for relative_root in ("app/bootstrap", "app/orchestration", "app/interfaces"):
        for path in (PROJECT_ROOT / relative_root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module: str | None = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in {"elfie", "nest"}:
                            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
                if module in {"elfie", "nest"} or (
                    module is not None
                    and (module.startswith("elfie.") or module.startswith("nest."))
                    and module not in {"elfie.public", "nest.public"}
                ):
                    offenders.append(path.relative_to(PROJECT_ROOT).as_posix())
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


def test_brain_tool_port_is_consumer_owned_and_the_legacy_skill_package_is_gone() -> (
    None
):
    assert getattr(ToolPort, "_is_protocol", False)
    assert ToolPort.__module__ == "elfie.brain.reasoning.tool_port"
    assert ToolRequest.__module__ == "elfie.brain.reasoning.tool_port"
    assert ToolResult.__module__ == "elfie.brain.reasoning.tool_port"
    assert not (ELFIE_ROOT / "skills").exists()


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
    assert EventWorkspace is not None


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


def test_elfie_life_system_contract_keeps_the_accepted_owners_and_gaps() -> None:
    english_contract = (PROJECT_ROOT / "docs/developer/contracts/elfie.md").read_text(
        encoding="utf-8"
    )
    chinese_contract = (
        PROJECT_ROOT / "docs/zh/developer/contracts/elfie.md"
    ).read_text(encoding="utf-8")
    conformance = (PROJECT_ROOT / "docs/developer/conformance/elfie.md").read_text(
        encoding="utf-8"
    )
    english_normalized = " ".join(english_contract.split())
    chinese_normalized = " ".join(chinese_contract.split())

    assert "**Contract version:** 2.3" in english_contract
    assert "**契约版本：** 2.3" in chinese_contract

    for owner in (
        "Event Workspace",
        "Orientation",
        "Selfhood",
        "Emotion",
        "Energy",
        "Motivation",
        "Memory",
        "Reasoning Core",
        "Persistent Activity",
        "Cognitive Consolidation",
    ):
        assert owner in english_contract
    for owner in (
        "事件工作区",
        "自我定位",
        "自我认知",
        "情绪",
        "能量",
        "动机",
        "记忆",
        "思考中枢",
        "跨回合活动",
        "心智整理",
    ):
        assert owner in chinese_contract

    assert "Profile answers the external objective question" in english_normalized
    assert "Profile 回答外层客观问题“是哪一只 Elfie”" in chinese_normalized
    assert "embodiments are mutually exclusive" in english_normalized
    assert "虚拟和实体具身互斥" in chinese_normalized
    assert "Genesis is a one-time creation flow" in english_normalized
    assert "Genesis 是一次性创建流程" in chinese_normalized
    assert "Genesis co-materializes Profile and Brain Selfhood" in english_normalized
    assert (
        "Ordinary Brain runtime does not read or synchronize Profile"
        in english_normalized
    )
    assert "cannot bind Selfhood to a Canon version" in english_normalized
    assert "并列物化 Profile 与 Brain Selfhood" in chinese_normalized
    assert "普通 Brain 运行期不读也不同步 Profile" in chinese_normalized
    assert "不能把 Selfhood 绑定到 Canon 版本" in chinese_normalized
    assert "It contains no world knowledge or Canon reference" in english_normalized
    assert "Profile 不得包含世界知识或 Canon 引用" in chinese_normalized
    assert (
        "A successful Genesis commit severs operational dependency"
        in english_normalized
    )
    assert "Genesis 成功提交后，必须切断" in chinese_normalized
    assert "Infrastructure -X-> semantic life compilation" in english_normalized
    assert "Infrastructure -X-> 生命语义编译" in chinese_normalized
    assert "| ELF-010 | P0 | closed |" in conformance
    assert "| ELF-013 | P0 | closed |" in conformance
    for gap_id in range(10, 18):
        assert f"ELF-{gap_id:03d}" in conformance


def test_current_genesis_design_uses_memory_owned_retention_and_severs_inputs() -> None:
    design = (
        PROJECT_ROOT / "docs/.internal/genesis-core-kernel-design-v0.2.md"
    ).read_text(encoding="utf-8")

    assert "`retention_profile=genesis`" in design
    assert "`half_life_days=3650`" in design
    assert "Memory 的版本化准入策略" in design
    assert "成功提交或终止失败后必须删除" in design
    assert "普通 Brain 运行只读取 Selfhood、Memory 与当前 Brain 状态" in design
    assert "`retention_days`" not in design
