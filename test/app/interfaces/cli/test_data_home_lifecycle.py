from __future__ import annotations

import stat
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle.facade import LifecycleFacade
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from infrastructure.persistence.layout.lifecycle_data_home import (
    LifecycleDataHomeAdapter,
)
from scripts import elfienest

LIFECYCLE = create_lifecycle_facade()


class _StartedSupervisor:
    def status(self):
        return RuntimeSnapshotV1(
            instance_id="test",
            tier=BackendTier.OFFLINE,
            phase=RuntimePhase.OFFLINE,
            desired_target=RuntimeTarget.CORE,
            generation=0,
        ).projection()

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        assert owner_id == "cli"
        return ServiceLifecycleResult(status="started", pid=42)


class _StoppedSupervisor:
    def __init__(self, command: tuple[str, ...] | None = None) -> None:
        self._command = command

    def stop(self) -> ServiceLifecycleResult:
        return ServiceLifecycleResult(status="stopped", command=self._command)


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


def test_started_service_remembers_selected_home_for_later_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Given start 显式根，When 后续命令无参数，Then 仍解析到同一数据根。"""
    source_root = tmp_path / "worktree"
    selected_home = tmp_path / "selected"
    monkeypatch.setattr(lifecycle_commands, "PROJECT_ROOT", source_root)
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *args, **kwargs: _StartedSupervisor(),
    )
    monkeypatch.setattr(
        lifecycle_commands, "_prepare_frontend_for_launch", lambda *_args: None
    )
    monkeypatch.setenv("ELFIENEST_RUNTIME_MODE", "development")
    monkeypatch.delenv("ELFIE_HOME", raising=False)
    command = ("python", "scripts/serve.py", "--data-home", str(selected_home))

    result = lifecycle_commands.start_background_service(LIFECYCLE, command)
    remembered = lifecycle_commands._data_home_for_command(
        LIFECYCLE,
        ("python", "scripts/serve.py"),
        use_remembered_home=True,
    )

    assert result.status == "started"
    assert remembered == selected_home.resolve()


def test_environment_data_home_takes_precedence_over_remembered_home(
    monkeypatch, tmp_path: Path
) -> None:
    adapter = LifecycleDataHomeAdapter()
    remembered_home = tmp_path / "remembered"
    environment_home = tmp_path / "environment"
    monkeypatch.setenv("ELFIE_HOME", str(environment_home))
    monkeypatch.setattr(adapter, "_remembered", lambda *_args: remembered_home)

    selected = adapter.select(
        None,
        project_root=tmp_path / "worktree",
        runtime_mode="development",
        use_remembered=True,
    )

    assert selected == environment_home.resolve()


def test_start_uses_remembered_lifecycle_home_for_status_and_start_consistency(
    monkeypatch,
) -> None:
    """Given a remembered data root, When start has no explicit root, Then it reuses it."""
    remembered_flags: list[bool] = []

    def supervisor(*_args, **kwargs) -> _StartedSupervisor:
        remembered_flags.append(kwargs["use_remembered_home"])
        return _StartedSupervisor()

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", supervisor)
    monkeypatch.setattr(
        lifecycle_commands, "_prepare_frontend_for_launch", lambda *_args: None
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
        command=("python", "scripts/serve.py"),
    )

    assert result.status == "started"
    assert remembered_flags == [True]


def test_installed_lifecycle_uses_the_packaged_application_root(
    monkeypatch, tmp_path: Path
) -> None:
    application_root = tmp_path / "ElfieNest.app"
    monkeypatch.setenv("ELFIENEST_PROJECT_ROOT", str(application_root))

    assert lifecycle_commands._runtime_project_root() == application_root.resolve()


def test_lifecycle_receipt_repairs_owner_only_control_directories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Given: an existing checkout-local control root with permissive modes.
    receipt_home = tmp_path / ".elfienest.local"
    runtime_dir = receipt_home / "runtime"
    runtime_dir.mkdir(parents=True, mode=0o755)
    adapter = LifecycleDataHomeAdapter()
    monkeypatch.setattr(
        adapter,
        "_receipt_path",
        lambda *_args: runtime_dir / "selected-data-home",
    )

    # When: the selected data-home receipt is recorded.
    adapter.remember(
        tmp_path / "selected",
        project_root=tmp_path,
        runtime_mode="development",
    )

    # Then: the control root, runtime directory, and receipt are owner-only.
    receipt = runtime_dir / "selected-data-home"
    assert stat.S_IMODE(receipt_home.stat().st_mode) == 0o700
    assert stat.S_IMODE(runtime_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


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


def test_stop_uses_remembered_lifecycle_home(monkeypatch) -> None:
    """Given 已选择的数据根，When stop，Then 从生命周期记录定位同一根。"""
    remembered_flags: list[bool] = []

    def supervisor(*_args, **kwargs) -> _StoppedSupervisor:
        remembered_flags.append(kwargs["use_remembered_home"])
        return _StoppedSupervisor()

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", supervisor)

    lifecycle_commands.stop_background_service(LIFECYCLE)

    assert remembered_flags == [True]


def test_restart_stops_remembered_home_and_reuses_recorded_command(monkeypatch) -> None:
    """Given 已运行命令，When restart，Then 从原根停止并以原参数启动。"""
    calls: list[bool] = []
    remembered: list[Path] = []
    recorded_command = ("python", "scripts/serve.py", "--data-home", "/tmp/selected")

    def supervisor(*_args, **kwargs):
        calls.append(kwargs.get("use_remembered_home", False))
        if len(calls) == 1:
            return _StoppedSupervisor(recorded_command)
        return _StartedSupervisor()

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", supervisor)
    monkeypatch.setattr(
        lifecycle_commands,
        "_remember_lifecycle_data_home",
        lambda _lifecycle, selected_home: remembered.append(selected_home),
    )

    result = lifecycle_commands.restart_background_service(LIFECYCLE)

    assert result.status == "started"
    assert calls == [True, False]
    assert remembered == [Path("/tmp/selected").resolve()]


def test_web_uses_remembered_lifecycle_home_to_find_running_service(
    monkeypatch, tmp_path: Path
) -> None:
    """Given restart 记录了临时根，When web，Then 查询同一根而非默认根。"""
    remembered_home = tmp_path / "remembered"
    selected_flags: list[bool] = []
    opened: list[str] = []
    command = ("python", "scripts/serve.py", "--port", "8100")

    def select_data_home(_explicit_home, *, use_remembered=False, **_kwargs):
        selected_flags.append(use_remembered)
        return remembered_home if use_remembered else tmp_path / "default"

    monkeypatch.setattr(LIFECYCLE, "select_data_home", select_data_home)
    monkeypatch.setattr(
        LIFECYCLE,
        "existing_service_command",
        lambda home, *_args: (42, command) if home == remembered_home else None,
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: port == 8100,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    result = lifecycle_commands.open_web_console(LIFECYCLE)

    assert result.status == "already_running"
    assert selected_flags == [True]
    assert opened == ["http://127.0.0.1:8100/"]


def test_status_reads_remembered_lifecycle_home(monkeypatch, tmp_path: Path) -> None:
    """Given 无显式参数，When status，Then 查询最近启动所选的数据根。"""
    remembered_flags: list[bool] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "_data_home_for_command",
        lambda *_args, **_kwargs: tmp_path / "selected",
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *_args: None)
    monkeypatch.setattr(LIFECYCLE, "default_port_statuses", lambda: ())

    def supervisor(*_args, **kwargs) -> _HealthSupervisor:
        remembered_flags.append(kwargs["use_remembered_home"])
        return _HealthSupervisor()

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", supervisor)

    lifecycle_commands.show_service_status(LIFECYCLE)

    assert remembered_flags == [True]
