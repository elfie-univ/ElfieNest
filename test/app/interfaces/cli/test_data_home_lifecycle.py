from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any, cast

import pytest

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle.facade import LifecycleFacade
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from scripts import elfienest

LIFECYCLE = create_lifecycle_facade()


@pytest.fixture(autouse=True)
def isolate_lifecycle_data_home(monkeypatch, tmp_path: Path) -> None:
    """Never let lifecycle command tests read or write the developer home."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfie-home"))
    monkeypatch.setattr(lifecycle_commands, "PROJECT_ROOT", tmp_path / "worktree")


class _HealthSupervisor:
    def status(self):
        return RuntimeSnapshotV1(
            instance_id="test",
            tier=BackendTier.OFFLINE,
            phase=RuntimePhase.OFFLINE,
            desired_target=RuntimeTarget.CORE,
            generation=0,
        ).projection()


def test_start_options_forward_resolved_data_home(monkeypatch, tmp_path: Path) -> None:
    """Given start 显式根，When 组装服务参数，Then 传递规范化绝对路径。"""
    monkeypatch.chdir(tmp_path)
    arguments = Namespace(
        port=None,
        godot_ws_port=None,
        data_home="selected",
        lan=True,
    )

    options = elfienest._service_options_from_args(arguments)

    assert options == (
        "--data-home",
        str((tmp_path / "selected").resolve()),
        "--lan",
    )


def test_installed_lifecycle_uses_the_packaged_application_root(
    monkeypatch, tmp_path: Path
) -> None:
    application_root = tmp_path / "ElfieNest.app"
    monkeypatch.setenv("ELFIENEST_PROJECT_ROOT", str(application_root))

    assert lifecycle_commands._runtime_project_root() == application_root.resolve()


def test_lifecycle_supervisor_uses_command_data_home(
    monkeypatch, tmp_path: Path
) -> None:
    """Given 服务命令显式根，When 构造 Supervisor，Then PID 与 Runtime 使用该根。"""
    selected_home = tmp_path / "selected"
    captured: dict[str, Path] = {}

    class Lifecycle:
        def select_data_home(self, explicit_home, **_kwargs):
            return Path(str(explicit_home)).resolve()

        def prepare_optional_component(self) -> None:
            return

        def runtime_supervisor(self, **kwargs: Any) -> _HealthSupervisor:
            captured["elfie_home"] = kwargs["elfie_home"]
            return _HealthSupervisor()

    command = ("python", "scripts/serve.py", "--data-home", str(selected_home))

    lifecycle_commands._supervisor_for(
        cast(LifecycleFacade, Lifecycle()), command, 8000
    )

    assert captured["elfie_home"] == selected_home.resolve()


def test_lifecycle_supervisor_publishes_selected_home_to_child(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Given 服务选中数据根，When 启动 Core，Then 子进程继承同一 ELFIE_HOME。"""
    selected_home = tmp_path / "selected"
    child_environments: list[dict[str, str]] = []

    class Lifecycle:
        def select_data_home(self, explicit_home, **_kwargs):
            return Path(str(explicit_home)).resolve()

        def prepare_optional_component(self) -> None:
            return

        def runtime_supervisor(self, **kwargs: Any) -> _HealthSupervisor:
            child_environments.append(dict(kwargs["child_environment"]))
            return _HealthSupervisor()

    command = ("python", "scripts/serve.py", "--data-home", str(selected_home))

    lifecycle_commands._supervisor_for(
        cast(LifecycleFacade, Lifecycle()), command, 8000
    )

    assert child_environments[0]["ELFIE_HOME"] == str(selected_home.resolve())
