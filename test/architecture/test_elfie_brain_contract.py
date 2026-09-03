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


def test_brain_contract_freezes_the_emotion_owner_and_review_boundary() -> None:
    english = _normalized("docs/developer/contracts/brain.md")
    chinese = _normalized("docs/zh/developer/contracts/brain.md")

    for token in (
        "Elfie's process-local affect, not an observed actor's affect",
        "happiness",
        "sadness",
        "anger",
        "fear",
        "surprise",
        "disgust",
        "pre-fast stable anchor",
        "does not deduplicate again",
        "owns no database, checkpoint or historical change-event ledger",
        "audio and image/vision transport",
    ):
        assert token in english
    for token in (
        "Elfie 自己的进程内情绪",
        "快速反应前的稳定 Anchor",
        "不再重复去重",
        "不拥有数据库、Checkpoint 或历史变化事件账本",
        "音频和图像/视觉传输",
    ):
        assert token in chinese

    assert "../designs/elfie/brain/elfie-emotion-system" in english
    assert "../conformance/elfie-emotion" in english
    assert "../designs/elfie/brain/elfie-emotion-system" in chinese
    assert "../conformance/elfie-emotion" in chinese
    assert "EMO-001" in _read("docs/developer/conformance/elfie-emotion.md")
    assert "EMO-002" in _read("docs/zh/developer/conformance/elfie-emotion.md")


def test_brain_contract_freezes_selfhood_and_the_four_block_model_header() -> None:
    english_raw = _read("docs/developer/contracts/brain.md")
    chinese_raw = _read("docs/zh/developer/contracts/brain.md")
    english = " ".join(english_raw.split())
    chinese = " ".join(chinese_raw.split())
    block_labels = (
        "APPLICATION_FRAME",
        "IDENTITY_CORE",
        "ADAPTIVE_SELF",
        "OPERATING_CONTRACT",
    )

    assert "**Contract version:** 1.5" in english_raw
    assert "**契约版本：** 1.5" in chinese_raw

    assert [english_raw.index(label) for label in block_labels] == sorted(
        english_raw.index(label) for label in block_labels
    )
    assert [chinese_raw.index(label) for label in block_labels] == sorted(
        chinese_raw.index(label) for label in block_labels
    )
    assert "[APPLICATION_FRAME]\n   {application_frame_text}" in english_raw
    assert "[IDENTITY_CORE]\n   {identity_core_text}" in english_raw
    assert "[ADAPTIVE_SELF]\n   {adaptive_self_text}" in english_raw
    assert "[OPERATING_CONTRACT]\n   {operating_contract_text}" in english_raw
    assert "不得新增 system 指令，也不得改变请求消息顺序或内容" in chinese
    assert (
        "must not add system instructions or change request message order/content"
        in english
    )
    assert "exactly two semantic layers" in english
    assert "语义上严格分两层" in chinese
    assert "Genesis is the only Selfhood initializer" in english
    assert "Genesis 是唯一 Selfhood 初始化者" in chinese
    assert "only a typed Memory-consolidation proposal" in english
    assert "最多允许 Memory 整理生成强类型 proposal" in chinese
    assert "emits no raw Big Five values or internal IDs" in english
    assert "不输出大五原始值或内部 ID" in chinese
    assert "must not fall back to `Elfie`, a generic persona" in english
    assert "不得 fallback 到 `Elfie`、通用 persona" in chinese
    assert (
        "Generic Brain continuity checkpoints must not contain or restore Selfhood"
        in english
    )
    assert "通用 Brain continuity checkpoint 不得包含或恢复 Selfhood" in chinese
    assert (
        "Memory must not persist or inject a second authoritative identity" in english
    )
    assert "Memory 不得持久化或注入第二套权威" in chinese
    assert "Ordinary Brain runtime" in english
    assert "普通 Brain 运行" in chinese
    assert "questionnaire answer, generation seed/policy trace" in english
    assert "问卷答案、生成 Seed/" in chinese
    assert "deleted after the creation transaction ends" in english
    assert "在创建事务结束后删除" in chinese
    assert "| SHD-002 | P0 | closed (v0.2 structural) |" in _read(
        "docs/developer/conformance/elfie-selfhood.md"
    )
    assert "../designs/elfie/brain/elfie-selfhood-and-fixed-model-header" in english_raw
    assert "../conformance/elfie-selfhood" in english_raw
    assert "../designs/elfie/brain/elfie-selfhood-and-fixed-model-header" in chinese_raw
    assert "../conformance/elfie-selfhood" in chinese_raw
    for gap_id in range(1, 8):
        marker = f"SHD-{gap_id:03d}"
        assert marker in _read("docs/developer/conformance/elfie-selfhood.md")
        assert marker in _read("docs/zh/developer/conformance/elfie-selfhood.md")


def test_brain_contract_freezes_reasoning_context_workspace_ownership() -> None:
    english_raw = _read("docs/developer/contracts/brain.md")
    chinese_raw = _read("docs/zh/developer/contracts/brain.md")
    english = " ".join(english_raw.split())
    chinese = " ".join(chinese_raw.split())

    assert "**Contract version:** 1.5" in english_raw
    assert "**契约版本：** 1.5" in chinese_raw
    for token in (
        "Event Workspace and Reasoning Context Workspace are distinct",
        "Memory owns no transient conversation tail",
        "Every Turn may perform baseline Memory Recall",
        "All Recall results used by one Run bind to one explicit Memory revision",
        "Before every model call, Reasoning rebuilds one provider-neutral model context",
        "Prompt-pressure compaction creates a source-linked `ContextSummary`",
        "`DIRECT` and `DELIBERATE` are Reasoning depth choices",
    ):
        assert token in english
    for token in (
        "Event Workspace 与 Reasoning Context Workspace 完全不同",
        "Memory 不拥有短期 conversation tail",
        "每个 Turn 都可以执行基础 Memory Recall",
        "同一 Run 使用的全部 Recall 必须绑定一个明确 Memory revision",
        "每次模型调用前，Reasoning 都从冻结快照",
        "Prompt 压力下的压缩生成 Reasoning 自有",
        "`DIRECT` 与 `DELIBERATE` 是根据上游提示",
    ):
        assert token in chinese

    current_boundary_docs = (
        "docs/developer/contracts/brain.md",
        "docs/developer/designs/elfie/brain/elfie-brain-ten-system-architecture.md",
        "docs/developer/designs/elfie/brain/elfie-memory-architecture.md",
    )
    assert all(
        "working memory" not in _read(path).lower() for path in current_boundary_docs
    )
    chinese_boundary_docs = (
        "docs/zh/developer/contracts/brain.md",
        "docs/zh/developer/designs/elfie/brain/elfie-brain-ten-system-architecture.md",
        "docs/zh/developer/designs/elfie/brain/elfie-memory-architecture.md",
    )
    assert all("工作记忆" not in _read(path) for path in chinese_boundary_docs)

    assert "../designs/elfie/brain/elfie-reasoning-core" in english_raw
    assert "../designs/elfie/brain/elfie-reasoning-core" in chinese_raw


def test_closed_brain_conformance_registers_do_not_return() -> None:
    retired_registers = (
        "docs/developer/conformance/brain.md",
        "docs/zh/developer/conformance/brain.md",
        "docs/developer/conformance/elfie-reasoning.md",
        "docs/zh/developer/conformance/elfie-reasoning.md",
    )

    assert all(not (PROJECT_ROOT / path).exists() for path in retired_registers)
    assert "conformance/brain" not in _read("docs/developer/contracts/brain.md")
    assert "conformance/brain" not in _read("docs/zh/developer/contracts/brain.md")
    assert "conformance/elfie-reasoning" not in _read(
        "docs/developer/contracts/brain.md"
    )
    assert "conformance/elfie-reasoning" not in _read(
        "docs/zh/developer/contracts/brain.md"
    )
    assert "Reasoning conformance register" not in _read(
        "docs/developer/decisions/0032-reasoning-context-workspace-ownership.md"
    )
    assert "Reasoning 一致性台账" not in _read(
        "docs/zh/developer/decisions/0032-reasoning-context-workspace-ownership.md"
    )
