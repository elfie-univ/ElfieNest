"""Machine guards for the authoritative service-lifecycle contract."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_service_lifecycle_contract_freezes_the_authoritative_state_model() -> None:
    english = _source("docs/developer/contracts/service-lifecycle.md")
    chinese = _source("docs/zh/developer/contracts/service-lifecycle.md")

    assert "**Contract version:** 1.1" in english
    assert "**契约版本：** 1.1" in chinese
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
    compact_chinese = " ".join(chinese.split())

    for token in (
        "${ELFIE_HOME:-~/.elfienest}",
        "`data-home activate`",
        "`selected-data-home`",
    ):
        assert token in english
        assert token in chinese
    assert (
        "Only `start`, `serve`, `restart` and `stop` accept `--data-home`"
        in compact_english
    )
    assert (
        "只有 `start`、`serve`、`restart` 和 `stop` 接受 `--data-home`"
        in compact_chinese
    )
    assert "must ignore caller `ELFIE_HOME`" in compact_english
    assert "必须忽略调用方 `ELFIE_HOME`" in compact_chinese
    assert "the default root is untouched" in compact_english
    assert "默认根保持不读不写" in compact_chinese
    assert "no `data-home activate` command" in compact_english
    assert "或 `data-home activate` 命令" in compact_chinese
    assert "an idle default must not prevent the selector" in compact_english
    assert "空闲默认根不能阻止选择器" in compact_chinese
    assert "execution are separate phases" in compact_english
    assert "目标选择与命令执行必须是两个阶段" in compact_chinese
    assert "`<source-root>/.elfienest-cli.local/`" in english
    assert "`<source-root>/.elfienest-cli.local/`" in chinese
    assert "outside every product data root" in compact_english
    assert "产品数据根之外" in compact_chinese
    assert "Every successfully resolved interactive target" in compact_english
    assert "每个成功解析的目标" in compact_chinese
    assert "do not compare it to the invoking checkout" in compact_english
    assert "不能与发起命令的 checkout 对比" in compact_chinese
    assert "report success only after the selected snapshot confirms" in compact_english
    assert (
        "只有在所选快照确认其承诺状态后才能报告成功" in compact_chinese
    )
    assert "Ports are never killed" in english
    assert "端口不能被“杀死”" in chinese


def test_service_lifecycle_governance_artifacts_remain_linked() -> None:
    required = {
        "docs/developer/decisions/0021-authoritative-service-lifecycle.md",
        "docs/zh/developer/decisions/0021-authoritative-service-lifecycle.md",
        "docs/developer/designs/service-lifecycle-state-machine.md",
        "docs/zh/developer/designs/service-lifecycle-state-machine.md",
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
