"""Architecture gates for the accepted Elfie Brain target contract."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _normalized(relative_path: str) -> str:
    return " ".join(_read(relative_path).split())


def test_brain_contract_keeps_ten_conceptual_owners_without_empty_packages() -> None:
    english = _normalized("docs/developer/contracts/brain.md")
    chinese = _normalized("docs/zh/developer/contracts/brain.md")

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
        assert owner in english
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
        assert owner in chinese

    assert "conceptual owners, not a requirement for ten processes" in english
    assert "不代表必须建立十个" in chinese


def test_brain_contract_keeps_turn_and_output_domain_isolation() -> None:
    english = _normalized("docs/developer/contracts/brain.md")
    chinese = _normalized("docs/zh/developer/contracts/brain.md")

    for source in ("Communication", "Embodied", "Internal"):
        assert source in english
        assert source in chinese
    assert "Receipts never create a fourth domain" in english
    assert "回执不形成第四个来源域" in chinese
    assert "exactly one `SourceDomain`" in english
    assert "一个 `SourceDomain`" in chinese
    assert "different conversations remain different Turns" in english
    assert "不同会话 必须形成不同 Turn" in chinese
    assert "at most one external execution domain" in english
    assert "至多请求一个外部执行域" in chinese
    for output in (
        "CommunicationDirective",
        "NervousSystemDirective",
        "PersistentActivityRequest",
        "No-op",
    ):
        assert output in english
        assert output in chinese


def test_brain_contract_keeps_activity_and_state_commit_boundaries() -> None:
    english = _normalized("docs/developer/contracts/brain.md")
    chinese = _normalized("docs/zh/developer/contracts/brain.md")

    assert "candidate, validation and commit" in english
    assert "候选—校验—提交" in chinese
    assert "Preflight has no durable or external side effect" in english
    assert "无副作用的 `ActivityDraft`" in chinese
    assert (
        "Motivation and Cognitive Consolidation cannot create Activity directly"
        in english
    )
    assert "动机和心智整理不能直接创建 Activity" in chinese
    assert (
        "Digital-message channels, Body control and device state are not Tools"
        in english
    )
    assert "数字通信渠道、身体控制和设备状态不是 Tool" in chinese


def test_closed_brain_conformance_registers_do_not_return() -> None:
    retired_registers = (
        "docs/developer/conformance/brain.md",
        "docs/zh/developer/conformance/brain.md",
    )

    assert all(not (PROJECT_ROOT / path).exists() for path in retired_registers)
    assert "conformance/brain" not in _read("docs/developer/contracts/brain.md")
    assert "conformance/brain" not in _read("docs/zh/developer/contracts/brain.md")
