"""Machine guards for the authoritative service-lifecycle contract."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_service_lifecycle_contract_freezes_the_authoritative_state_model() -> None:
    english = _source("docs/developer/contracts/service-lifecycle.md")
    chinese = _source("docs/zh/developer/contracts/service-lifecycle.md")

    assert "**Contract version:** 1.4" in english
    assert "**契约版本：** 1.4" in chinese
    for token in ("`OFFLINE`", "`CORE_READY`", "`WORLD_READY`"):
        assert token in english
        assert token in chinese
    for token in ("Common Food", "Emergency Food", "Inactive models"):
        assert token in english
    for token in ("常用粮", "保底粮", "非活跃模型"):
        assert token in chinese
    assert "sole writer of Runtime lifecycle state" in english
    assert "Runtime 生命周期状态的唯一写入者" in chinese
    assert "App Food/model-capability" in english
    assert "App Food/模型能力服务" in chinese
    assert "`desired_target` and `wait_target`" in english
    assert "`desired_target` 和 `wait_target`" in chinese


def test_service_lifecycle_contract_freezes_entrypoint_and_process_ownership() -> None:
    english = _source("docs/developer/contracts/service-lifecycle.md")
    chinese = _source("docs/zh/developer/contracts/service-lifecycle.md")

    for source in (english, chinese):
        assert "`elfienest start`" in source
        assert "`./elfienest.sh`" in source
        assert "`EXTERNAL`" in source
        assert "`ELFIENEST_OWNED`" in source
        assert "SESSION_OWNED" not in source
        assert "BUSY_STOPPING" in source
    assert "never installs Python/Node dependencies" in english
    assert "不得安装 Python/Node 依赖" in chinese
    assert "Install or update" in english
    assert "安装或升级" in chinese
    assert "PID, port, process name" in english
    assert "PID、端口、进程名" in chinese


def test_service_lifecycle_contract_freezes_data_root_task_context() -> None:
    english = _source("docs/developer/contracts/service-lifecycle.md")
    chinese = _source("docs/zh/developer/contracts/service-lifecycle.md")
    compact_english = " ".join(english.split())
    compact_chinese = " ".join(chinese.split()).replace("、 ", "、")

    required_pairs = (
        ("${ELFIE_HOME:-~/.elfienest}", "${ELFIE_HOME:-~/.elfienest}"),
        ("`selected-data-home`", "`selected-data-home`"),
        (
            "Only `start`, `serve`, `restart` and `stop` accept `--data-home`",
            "只有 `start`、`serve`、`restart`、`stop` 接受 `--data-home`",
        ),
        ("ignores caller `ELFIE_HOME`", "忽略调用方 `ELFIE_HOME`"),
        ("there is no public `data-home` command", "不存在公开 `data-home` 命令"),
        (
            "TTY selection always requires explicit confirmation",
            "TTY 选择始终需要显式确认",
        ),
        ("Failure there does not fall through", "在该目标失败时不能 fallback"),
        (
            "`<source-root>/.elfienest.local/runtime/cli/`",
            "`<source-root>/.elfienest.local/runtime/cli/`",
        ),
        ("its presence never grants authority", "存在它也不能授予权限"),
        (
            "`web`, `mobile` and `desktop` only open an existing healthy target",
            "`web`、`mobile`、`desktop` 只打开已有健康目标",
        ),
        (
            "Ports are endpoints, never identity or cleanup targets",
            "端口只是 endpoint，不是身份或清理目标",
        ),
        (
            "report success only after the selected snapshot confirms",
            "只有在所选快照确认承诺状态后才能报告成功",
        ),
    )
    for english_token, chinese_token in required_pairs:
        assert english_token in compact_english
        assert chinese_token in compact_chinese


def test_service_lifecycle_governance_artifacts_remain_linked() -> None:
    required = {
        "docs/developer/decisions/0021-authoritative-service-lifecycle.md",
        "docs/zh/developer/decisions/0021-authoritative-service-lifecycle.md",
        "docs/developer/designs/app/service-lifecycle-state-machine.md",
        "docs/zh/developer/designs/app/service-lifecycle-state-machine.md",
        "docs/developer/conformance/service-lifecycle.md",
        "docs/zh/developer/conformance/service-lifecycle.md",
    }
    assert all((PROJECT_ROOT / path).is_file() for path in required)

    english_adr = _source(
        "docs/developer/decisions/0021-authoritative-service-lifecycle.md"
    )
    chinese_adr = _source(
        "docs/zh/developer/decisions/0021-authoritative-service-lifecycle.md"
    )
    assert "ADR-0014 remains historical evidence" in english_adr
    assert "ADR-0014 继续作为" in chinese_adr
    assert "LFC-001" in _source("docs/developer/conformance/service-lifecycle.md")
    assert "LFC-009" in _source("docs/zh/developer/conformance/service-lifecycle.md")
    assert "LFC-010" in _source("docs/developer/conformance/service-lifecycle.md")
    assert "LFC-010" in _source("docs/zh/developer/conformance/service-lifecycle.md")
