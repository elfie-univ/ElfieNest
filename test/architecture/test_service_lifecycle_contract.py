"""Machine guards for the authoritative service-lifecycle contract."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_service_lifecycle_contract_freezes_the_authoritative_state_model() -> None:
    english = _source("docs/developer/contracts/service-lifecycle.md")
    chinese = _source("docs/zh/developer/contracts/service-lifecycle.md")

    assert "**Contract version:** 1.0" in english
    assert "**契约版本：** 1.0" in chinese
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
