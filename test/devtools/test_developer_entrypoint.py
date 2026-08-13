from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import pytest

import devtools.__main__ as developer_main
import devtools.elfie_lab.app as elfie_lab_app
import devtools.nest_lab.__main__ as nest_lab_main
import devtools.nest_lab.app as nest_lab_app
from devtools.entrypoint import available_tools, resolve_tool


def test_developer_tools_are_explicit_and_do_not_include_user_service() -> None:
    # Given
    tools = available_tools()

    # When
    names = tuple(tool.name for tool in tools)

    # Then
    assert names == ("elfie-lab", "nest-lab")
    assert "serve" not in names


def test_nest_lab_resolution_uses_isolated_data_root(tmp_path: Path) -> None:
    # Given
    tool = resolve_tool("nest-lab", tmp_path)

    # When / Then
    assert tool.module == "devtools.nest_lab"
    assert tool.default_port == 9002
    assert tool.data_root == tmp_path / "nest_lab"


def test_default_developer_tools_resolve_under_developer_home(
    monkeypatch, tmp_path: Path
) -> None:
    """Developer Tool 默认根不得落入生产 ELFIE_HOME。"""
    production_home = tmp_path / "production"
    developer_home = tmp_path / "developer"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(developer_home))

    tools = available_tools()

    assert tuple(tool.data_root for tool in tools) == (
        developer_home / "elfie_lab",
        developer_home / "nest_lab",
    )


def test_elfie_lab_opens_default_url_when_server_becomes_ready(
    monkeypatch,
) -> None:
    # Given
    opened_urls: list[str] = []
    served_apps: list[str] = []

    def create_ready_app(
        _data_dir: str,
        *,
        on_ready: Callable[[], None],
    ) -> str:
        on_ready()
        return "elfie-lab-app"

    def serve(app: str, *, host: str, port: int, access_log: bool) -> None:
        assert host == "127.0.0.1"
        assert port == 9001
        assert access_log is False
        served_apps.append(app)

    monkeypatch.setattr(elfie_lab_app, "create_app", create_ready_app)
    monkeypatch.setattr(developer_main.uvicorn, "run", serve)
    monkeypatch.setattr(developer_main.webbrowser, "open", opened_urls.append)
    monkeypatch.setattr(
        developer_main,
        "restart_default_lab",
        lambda _tool, _workspace: None,
    )

    # When
    exit_code = developer_main.main(["elfie-lab"])

    # Then
    assert exit_code == 0
    opened_url = urlparse(opened_urls[0])
    assert opened_url.geturl().startswith("http://127.0.0.1:9001/?run=")
    assert parse_qs(opened_url.query)["run"]
    assert served_apps == ["elfie-lab-app"]


def test_default_elfie_lab_launch_restarts_its_previous_default_instance(
    monkeypatch,
) -> None:
    # Given
    restarted_tools: list[str] = []

    def create_ready_app(
        _data_dir: str,
        *,
        on_ready: Callable[[], None],
    ) -> str:
        on_ready()
        return "elfie-lab-app"

    monkeypatch.setattr(elfie_lab_app, "create_app", create_ready_app)
    monkeypatch.setattr(
        developer_main.uvicorn,
        "run",
        lambda _app, **_kwargs: None,
    )
    monkeypatch.setattr(developer_main.webbrowser, "open", lambda _url: True)
    monkeypatch.setattr(
        developer_main,
        "restart_default_lab",
        lambda tool, _workspace: restarted_tools.append(tool.name),
    )

    # When
    developer_main.main(["elfie-lab"])

    # Then
    assert restarted_tools == ["elfie-lab"]


def test_explicit_lab_port_keeps_parallel_launch_behavior(monkeypatch) -> None:
    # Given
    restarted_tools: list[str] = []

    def create_ready_app(
        _data_dir: str,
        *,
        on_ready: Callable[[], None],
    ) -> str:
        on_ready()
        return "elfie-lab-app"

    monkeypatch.setattr(elfie_lab_app, "create_app", create_ready_app)
    monkeypatch.setattr(
        developer_main.uvicorn,
        "run",
        lambda _app, **_kwargs: None,
    )
    monkeypatch.setattr(developer_main.webbrowser, "open", lambda _url: True)
    monkeypatch.setattr(
        developer_main,
        "restart_default_lab",
        lambda tool, _workspace: restarted_tools.append(tool.name),
    )

    # When
    developer_main.main(["elfie-lab", "--port", "8878"])

    # Then
    assert restarted_tools == []


def test_elfie_lab_unified_entrypoint_rejects_remote_binding() -> None:
    # Given / When / Then
    with pytest.raises(SystemExit, match="2"):
        developer_main.main(["elfie-lab", "--host", "0.0.0.0"])


def test_nest_lab_opens_its_page_and_passes_the_runtime_ports(monkeypatch) -> None:
    # Given
    opened_urls: list[str] = []
    served_apps: list[str] = []

    def create_ready_app(
        _data_dir: Path,
        *,
        http_port: int,
        godot_ws_port: int,
        on_ready: Callable[[], None],
    ) -> str:
        assert (http_port, godot_ws_port) == (8892, 8999)
        on_ready()
        return "nest-lab-app"

    def serve(app: str, *, host: str, port: int, access_log: bool) -> None:
        assert (host, port) == ("127.0.0.1", 8892)
        assert access_log is False
        served_apps.append(app)

    monkeypatch.setattr(nest_lab_app, "create_app", create_ready_app)
    monkeypatch.setattr(developer_main.uvicorn, "run", serve)
    monkeypatch.setattr(developer_main.webbrowser, "open", opened_urls.append)

    # When
    exit_code = developer_main.main(
        ["nest-lab", "--port", "8892", "--godot-ws-port", "8999"]
    )

    # Then
    assert exit_code == 0
    opened_url = urlparse(opened_urls[0])
    assert opened_url.geturl().startswith("http://127.0.0.1:8892/?run=")
    assert parse_qs(opened_url.query)["run"]
    assert served_apps == ["nest-lab-app"]


def test_nest_lab_unified_entrypoint_rejects_remote_binding() -> None:
    with pytest.raises(SystemExit, match="2"):
        developer_main.main(["nest-lab", "--host", "0.0.0.0"])


def test_nest_lab_direct_module_entrypoint_rejects_remote_binding(monkeypatch) -> None:
    monkeypatch.setattr(
        developer_main.sys,
        "argv",
        ["devtools.nest_lab", "--host", "0.0.0.0"],
    )

    with pytest.raises(SystemExit, match="2"):
        nest_lab_main.main()
