from __future__ import annotations

from pathlib import Path

import pytest

from devtools.entrypoint import resolve_tool
from devtools.lab_restart import (
    ForeignPortOwnerError,
    RestartInspector,
    restart_default_lab,
)


class FakeRestartInspector:
    def __init__(
        self,
        listeners: dict[int, tuple[int, ...]],
        commands: dict[int, tuple[str, ...]],
        working_directories: dict[int, Path],
    ) -> None:
        self.listeners = listeners
        self.commands = commands
        self.working_directories = working_directories
        self.terminated: list[int] = []
        self.waited_ports: tuple[int, ...] | None = None

    def listening_pids(self, port: int) -> tuple[int, ...]:
        return self.listeners.get(port, ())

    def command(self, pid: int) -> tuple[str, ...]:
        return self.commands[pid]

    def cwd(self, pid: int) -> Path:
        return self.working_directories[pid]

    def terminate(self, pid: int) -> None:
        self.terminated.append(pid)

    def wait_until_free(self, ports: tuple[int, ...]) -> bool:
        self.waited_ports = ports
        return True


def test_restart_default_nest_lab_stops_only_its_current_worktree_process(
    tmp_path: Path,
) -> None:
    # Given
    workspace = tmp_path / "ElfieNest"
    tool = resolve_tool("nest-lab", tmp_path)
    inspector: RestartInspector = FakeRestartInspector(
        listeners={9002: (71,), 9003: (71,)},
        commands={
            71: (
                str(workspace / ".venv/bin/python3"),
                "-m",
                "devtools",
                "nest-lab",
            )
        },
        working_directories={71: workspace},
    )

    # When
    restart_default_lab(tool, workspace, inspector)

    # Then
    assert inspector.terminated == [71]
    assert inspector.waited_ports == (9002, 9003)


def test_restart_default_lab_rejects_an_unrelated_process_on_its_port(
    tmp_path: Path,
) -> None:
    # Given
    tool = resolve_tool("elfie-lab", tmp_path)
    inspector: RestartInspector = FakeRestartInspector(
        listeners={9001: (72,)},
        commands={72: ("/usr/local/bin/other-server", "--port", "9001")},
        working_directories={72: tmp_path / "other-project"},
    )

    # When / Then
    with pytest.raises(ForeignPortOwnerError, match="9001"):
        restart_default_lab(tool, tmp_path / "ElfieNest", inspector)
    assert inspector.terminated == []
