from __future__ import annotations

from pathlib import Path
from typing import Callable

import devtools.__main__ as developer_main
import devtools.elfie_lab.app as elfie_lab_app
from devtools.entrypoint import available_tools, resolve_tool


def test_developer_tools_are_explicit_and_do_not_include_user_service() -> None:
    # Given
    tools = available_tools()

    # When
    names = tuple(tool.name for tool in tools)

    # Then
    assert names == ("elfie-lab", "runtime-lab", "nest-lab")
    assert "serve" not in names


def test_nest_lab_resolution_uses_isolated_data_root(tmp_path: Path) -> None:
    # Given
    tool = resolve_tool("nest-lab", tmp_path)

    # When / Then
    assert tool.module == "devtools.nest_lab"
    assert tool.default_port == 8890
    assert tool.data_root == tmp_path / "nest_lab"


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

    def serve(app: str, *, host: str, port: int) -> None:
        assert host == "127.0.0.1"
        assert port == 8877
        served_apps.append(app)

    monkeypatch.setattr(elfie_lab_app, "create_app", create_ready_app)
    monkeypatch.setattr(developer_main.uvicorn, "run", serve)
    monkeypatch.setattr(developer_main.webbrowser, "open", opened_urls.append)

    # When
    exit_code = developer_main.main(["elfie-lab"])

    # Then
    assert exit_code == 0
    assert opened_urls == ["http://127.0.0.1:8877/"]
    assert served_apps == ["elfie-lab-app"]
