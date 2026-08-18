from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.interfaces.cli import lifecycle_commands
from app.interfaces.cli.target_context import resolve_cli_target
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.target_resolution import EntrypointMode
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from scripts import elfienest


class _Lifecycle:
    def default_service_command(self, options=()):
        return ("python", "scripts/serve.py", *tuple(options))


def test_installed_target_resolution_is_shared_by_all_data_commands(
    tmp_path: Path,
) -> None:
    installed_home = (tmp_path / "installed-home").resolve()
    commands = (
        "start",
        "serve",
        "restart",
        "stop",
        "status",
        "web",
        "mobile",
        "desktop",
        "config",
        "owner",
        "doctor",
        "db",
        "uninstall",
    )

    for command in commands:
        target = resolve_cli_target(
            _Lifecycle(),
            command=command,
            mode=EntrypointMode.INSTALLED,
            source_root=tmp_path / "checkout",
            invoking_cwd=tmp_path,
            installed_environment={"ELFIE_HOME": str(installed_home)},
        )
        assert target.home == installed_home


def test_installed_data_commands_receive_the_selected_database_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    expected_db = str(elfienest.get_db_path_for_home(selected_home))
    captured: dict[str, str] = {}

    configuration = SimpleNamespace(
        providers=object(),
        food=object(),
        capabilities=object(),
        settings=object(),
        principal=object(),
    )
    monkeypatch.setattr(
        elfienest,
        "build_cli_configuration",
        lambda db_path: captured.__setitem__("config", db_path) or configuration,
    )
    monkeypatch.setattr(elfienest, "run_config_tui", lambda *_args: None)
    monkeypatch.setattr(
        elfienest,
        "build_accounts_service",
        lambda db_path: captured.__setitem__("owner", db_path) or object(),
    )
    monkeypatch.setattr(elfienest, "build_terminal_menu", lambda: object())
    monkeypatch.setattr(elfienest, "run_owner_menu", lambda *_args: 0)
    monkeypatch.setattr(
        elfienest,
        "run_doctor",
        lambda _lifecycle, **kwargs: (
            captured.__setitem__("doctor", str(kwargs["selected_home"])) or 0
        ),
    )
    monkeypatch.setattr(
        elfienest,
        "run_uninstall_menu",
        lambda _lifecycle, _menu, **kwargs: (
            captured.__setitem__("uninstall", str(kwargs["selected_home"])) or 0
        ),
    )
    monkeypatch.setattr(
        elfienest,
        "build_operations_facade",
        lambda db_path: captured.__setitem__("db", db_path) or object(),
    )
    monkeypatch.setattr(elfienest, "dispatch_db", lambda operations, _subcmd: None)

    for command in ("config", "owner", "doctor", "db", "uninstall"):
        args = Namespace(command=command, config_path=None, db_command=None)
        try:
            elfienest._dispatch_command(
                args,
                _Lifecycle(),
                selected_home=selected_home,
            )
        except SystemExit as error:
            assert error.code == 0

    assert captured == {
        "config": expected_db,
        "owner": expected_db,
        "doctor": str(selected_home),
        "db": expected_db,
        "uninstall": str(selected_home),
    }


def test_installed_view_commands_validate_the_controller_root(
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    calls: list[Path] = []

    class Lifecycle:
        def controller_request(self, _command, *, expected_data_home):
            calls.append(expected_data_home)
            return None

    lifecycle = Lifecycle()
    elfienest._verify_installed_controller_target(
        lifecycle,
        selected_home,
        command="status",
        require_controller=False,
    )
    with pytest.raises(elfienest.DataHomeSelectionError):
        elfienest._verify_installed_controller_target(
            lifecycle,
            selected_home,
            command="web",
            require_controller=True,
        )

    assert calls == [selected_home, selected_home]


def test_web_health_probe_requires_the_selected_runtime_identity() -> None:
    class Lifecycle:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def http_get(self, _url, *, timeout_seconds):
            assert timeout_seconds == 2.0
            return SimpleNamespace(
                status=200,
                body=json.dumps(self.payload).encode("utf-8"),
            )

    matching = Lifecycle({"status": "ok", "instance_id": "task-a", "generation": 7})
    occupied_by_another_task = Lifecycle(
        {"status": "ok", "instance_id": "task-b", "generation": 7}
    )

    assert lifecycle_commands._web_is_healthy(
        matching,
        17870,
        expected_identity=("task-a", 7),
    )
    assert not lifecycle_commands._web_is_healthy(
        occupied_by_another_task,
        17870,
        expected_identity=("task-a", 7),
    )


def test_port_diagnosis_uses_selected_runtime_endpoints_without_command_ports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    captured: dict[str, object] = {}

    class Lifecycle:
        def runtime_projection(self, home):
            assert home == selected_home
            return SimpleNamespace(
                endpoints=(
                    SimpleNamespace(name="http", port=19100),
                    SimpleNamespace(name="godot_ws", port=19101),
                )
            )

    def diagnose_ports(*, lifecycle, ports):
        captured["lifecycle"] = lifecycle
        captured["ports"] = ports
        return {}

    monkeypatch.setattr(
        "app.interfaces.cli.doctor_commands.diagnose_ports", diagnose_ports
    )

    lifecycle = Lifecycle()
    result = lifecycle_commands._diagnose_ports_for_command(
        lifecycle,
        ("python", "scripts/serve.py"),
        selected_home=selected_home,
    )

    assert result == {}
    assert captured["lifecycle"] is lifecycle
    assert captured["ports"] == (19100, 19101)


@pytest.mark.parametrize("command", ("start", "restart", "serve", "stop"))
def test_dispatch_passes_resolved_home_to_lifecycle_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    captured: dict[str, Path] = {}

    def record(*_args, **kwargs):
        captured[command] = kwargs["selected_home"]
        return ServiceLifecycleResult(status="started")

    function_name = (
        "run_foreground_service"
        if command == "serve"
        else f"{command}_background_service"
    )
    monkeypatch.setattr(elfienest, function_name, record)
    args = Namespace(
        command=command,
        port=None,
        godot_ws_port=None,
        data_home=None,
        owner_id=None,
        json=False,
        progress_json=False,
    )

    elfienest._dispatch_command(
        args,
        _Lifecycle(),
        selected_home=selected_home,
    )

    assert captured[command] == selected_home


def test_supervisor_uses_passed_home_without_resolving_again(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    captured: dict[str, Path] = {}

    class Lifecycle:
        def select_data_home(self, *_args, **_kwargs):
            raise AssertionError("the already-resolved target must be reused")

        def runtime_supervisor(self, **kwargs):
            captured["home"] = kwargs["elfie_home"]
            return SimpleNamespace()

    lifecycle_commands._supervisor_for(
        Lifecycle(),
        ("python", "scripts/serve.py"),
        8000,
        selected_home=selected_home,
    )

    assert captured["home"] == selected_home


def test_start_reuses_passed_home_for_supervisor_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    command = ("python", "scripts/serve.py", "--port", "8123")
    captured: dict[str, Path] = {}

    class Supervisor:
        def status(self):
            return RuntimeSnapshotV1(
                tier=BackendTier.OFFLINE,
                phase=RuntimePhase.OFFLINE,
                desired_target=RuntimeTarget.CORE,
            ).projection()

        def start(self, *, owner_id: str):
            assert owner_id == "cli"
            return ServiceLifecycleResult(status="started", pid=42, command=command)

    def build_supervisor(*_args, **kwargs):
        captured["home"] = kwargs["selected_home"]
        return Supervisor()

    class NoResolveLifecycle(_Lifecycle):
        def select_data_home(self, *_args, **_kwargs):
            raise AssertionError("target must not be resolved again")

    monkeypatch.setattr(
        lifecycle_commands,
        "_data_home_launch_error",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_select_automatic_ports",
        lambda _lifecycle, launch_command, _home, **_kwargs: tuple(launch_command),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda *_args: None,
    )
    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)

    result = lifecycle_commands.start_background_service(
        NoResolveLifecycle(),
        command,
        selected_home=selected_home,
    )

    assert result.status == "started"
    assert captured["home"] == selected_home
